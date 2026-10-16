"""
Cryptographic Security, Password Hashing, Session Token Signing, and Rate Limiting.
"""

import time
import hmac
import hashlib
import secrets
import logging
import base64
from typing import Optional, Dict, Tuple, List, Any
import bcrypt
from cryptography.fernet import Fernet

from backend.app.core.config import settings

logger = logging.getLogger("security")

# Rate limiting storage: {ip_address: [timestamp, timestamp, ...]}
_FAILED_ATTEMPTS: Dict[str, List[float]] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300  # 5 minutes


def _get_secret_bytes() -> bytes:
    """Returns the secret key as bytes for HMAC operations."""
    return settings.SECRET_KEY.encode("utf-8")


def _get_fernet() -> Fernet:
    """
    Derives a 32-byte urlsafe base64 key for Fernet symmetric encryption.
    Uses dedicated ENCRYPTION_KEY if provided, otherwise derives a dedicated
    isolated key from SECRET_KEY using a domain separation salt.
    """
    if settings.ENCRYPTION_KEY:
        digest = hashlib.sha256(settings.ENCRYPTION_KEY.encode("utf-8")).digest()
    else:
        # Cryptographic domain separation so JWT secret is not reused directly for Fernet
        digest = hashlib.sha256(
            settings.SECRET_KEY.encode("utf-8") + b"::SESSION_FERNET_CIPHER_V2"
        ).digest()
    key_b64 = base64.urlsafe_b64encode(digest)
    return Fernet(key_b64)


# Single-use short-lived WebSocket authentication tickets
_WS_TICKETS: Dict[str, Dict[str, Any]] = {}


def create_ws_ticket(username: str, role: str = "user") -> str:
    """Generates a single-use ticket valid for 60 seconds for WebSocket connection auth."""
    ticket = secrets.token_urlsafe(32)
    _WS_TICKETS[ticket] = {
        "username": username,
        "role": role,
        "expires_at": time.time() + 60.0,
    }
    return ticket


def consume_ws_ticket(ticket: str) -> Optional[Dict[str, str]]:
    """Validates and consumes a one-time WebSocket ticket (cannot be reused)."""
    if not ticket:
        return None
    now = time.time()
    # Prune expired tickets
    for k in list(_WS_TICKETS.keys()):
        if _WS_TICKETS[k]["expires_at"] < now:
            _WS_TICKETS.pop(k, None)

    item = _WS_TICKETS.pop(ticket, None)
    if not item or item["expires_at"] < now:
        return None
    return {"username": item["username"], "role": item["role"]}


def encrypt_text(plain_text: str) -> str:
    """Encrypts plain text with Fernet (used for MongoDB session storage)."""
    if not plain_text:
        return ""
    f = _get_fernet()
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_text(cipher_text: str) -> str:
    """Decrypts cipher text with Fernet."""
    if not cipher_text:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.warning(f"Decryption failed: {e}")
        return ""


# Password Hashing
def hash_password(plain_password: str) -> str:
    """Hashes a password using bcrypt with salt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain_password.strip().encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.strip().encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception as e:
        logger.error(f"Error verifying password hash: {e}")
        return False


# Rate Limiting
def check_rate_limit(client_ip: str) -> Tuple[bool, Optional[str]]:
    """Checks if client IP exceeded failed login attempts."""
    now = time.time()
    cutoff = now - LOCKOUT_WINDOW_SECONDS

    # Prune the global map so it cannot grow unbounded under scanner traffic
    if len(_FAILED_ATTEMPTS) > 1000:
        for ip in list(_FAILED_ATTEMPTS.keys()):
            live = [t for t in _FAILED_ATTEMPTS[ip] if t > cutoff]
            if live:
                _FAILED_ATTEMPTS[ip] = live
            else:
                _FAILED_ATTEMPTS.pop(ip, None)

    attempts = [t for t in _FAILED_ATTEMPTS.get(client_ip, []) if t > cutoff]
    _FAILED_ATTEMPTS[client_ip] = attempts

    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        wait_seconds = int(LOCKOUT_WINDOW_SECONDS - (now - attempts[0]))
        return (
            False,
            f"Too many failed login attempts. Locked out for {max(wait_seconds, 1)} seconds.",
        )
    return True, None


def record_failed_attempt(client_ip: str):
    """Records a failed login attempt for the client IP."""
    now = time.time()
    if client_ip not in _FAILED_ATTEMPTS:
        _FAILED_ATTEMPTS[client_ip] = []
    _FAILED_ATTEMPTS[client_ip].append(now)


def reset_failed_attempts(client_ip: str):
    """Resets failed login attempts for client IP upon successful login."""
    _FAILED_ATTEMPTS.pop(client_ip, None)


# Session Token Generation & Verification
def create_session_token(
    username: str, role: str = "user", token_version: int = 1
) -> Tuple[str, str]:
    """Generates a signed HMAC session token containing timestamp, nonce, csrf_token, username, role, token_version."""
    secret = _get_secret_bytes()
    created_at = str(int(time.time()))
    nonce = secrets.token_hex(8)
    csrf_token = secrets.token_hex(16)
    u_clean = username.strip().lower()
    r_clean = role.strip().lower()
    v_clean = str(token_version)

    payload = f"{created_at}:{nonce}:{csrf_token}:{u_clean}:{r_clean}:{v_clean}"
    sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = f"{payload}:{sig}"
    return token, csrf_token


def verify_session_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Verifies HMAC signature, checks expiration, and extracts session claims."""
    if not token or ":" not in token:
        return None

    parts = token.split(":")
    secret = _get_secret_bytes()

    # Format: created_at:nonce:csrf_token:username:role:token_version:sig (7 parts)
    if len(parts) == 7:
        created_at_str, nonce, csrf_token, username, role, token_version_str, sig = parts
        try:
            created_at = int(created_at_str)
            token_version = int(token_version_str)
        except ValueError:
            return None

        if time.time() - created_at > settings.SESSION_MAX_AGE_SECONDS:
            return None

        expected_payload = f"{created_at_str}:{nonce}:{csrf_token}:{username}:{role}:{token_version_str}"
        expected_sig = hmac.new(
            secret, expected_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            return None

        return {
            "created_at": created_at_str,
            "csrf_token": csrf_token,
            "username": username,
            "role": role,
            "token_version": token_version,
        }

    # Format: created_at:nonce:csrf_token:username:role:sig (6 parts - backward compatibility)
    elif len(parts) == 6:
        created_at_str, nonce, csrf_token, username, role, sig = parts
        try:
            created_at = int(created_at_str)
        except ValueError:
            return None

        if time.time() - created_at > settings.SESSION_MAX_AGE_SECONDS:
            return None

        expected_payload = f"{created_at_str}:{nonce}:{csrf_token}:{username}:{role}"
        expected_sig = hmac.new(
            secret, expected_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            return None

        return {
            "created_at": created_at_str,
            "csrf_token": csrf_token,
            "username": username,
            "role": role,
            "token_version": 1,
        }

    # Legacy fallback format: created_at:nonce:csrf_token:sig (4 parts)
    elif len(parts) == 4:
        created_at_str, nonce, csrf_token, sig = parts
        try:
            created_at = int(created_at_str)
        except ValueError:
            return None

        if time.time() - created_at > settings.SESSION_MAX_AGE_SECONDS:
            return None

        expected_payload = f"{created_at_str}:{nonce}:{csrf_token}"
        expected_sig = hmac.new(
            secret, expected_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            return None

        return {
            "created_at": created_at_str,
            "csrf_token": csrf_token,
            "username": settings.ADMIN_USERNAME,
            "role": "admin",
        }

    return None
