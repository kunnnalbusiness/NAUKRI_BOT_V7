"""
FastAPI Security Dependencies.
Supports both Bearer Token Header (Authorization: Bearer <token>) and Cookie authentication.
Enforces strict Role-Based Access Control (require_admin) and user isolation.
"""

import hmac
from typing import Dict, Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.app.core.config import settings
from backend.app.core.security import verify_session_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_claims(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Dict[str, str]:
    """
    Extracts session claims from Authorization: Bearer <token> or Session Cookie.
    Dual-mode support guarantees authentication works reliably even behind strict proxies.
    """
    token: Optional[str] = None

    # 1. Check Bearer token header first (preferred for React SPA)
    if auth_header and auth_header.credentials:
        token = auth_header.credentials.strip()

    # 2. Check Cookie fallback
    if not token:
        token = request.cookies.get(settings.SESSION_COOKIE_NAME)

    session_data = verify_session_token(token)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Session is invalid or expired.",
        )

    # Invalidate token if token_version is older than stored user token_version (e.g. after password reset)
    from backend.app.db.mongo import get_user

    u_doc = get_user(session_data.get("username", ""))
    if u_doc:
        current_v = int(u_doc.get("token_version", 1))
        token_v = int(session_data.get("token_version", 1))
        if token_v < current_v:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Session has been revoked.",
            )

    # Attach to request state for convenient access
    request.state.user = session_data
    return session_data


async def require_auth(
    claims: Dict[str, str] = Depends(get_current_user_claims)
) -> Dict[str, str]:
    """FastAPI dependency: requires valid authenticated session."""
    return claims


async def require_admin(
    claims: Dict[str, str] = Depends(require_auth)
) -> Dict[str, str]:
    """
    FastAPI dependency: strictly verifies that the authenticated user possesses 'admin' role.
    Raises 403 Forbidden for regular users attempting to access admin endpoints.
    """
    role = claims.get("role", "user")
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin privileges required.",
        )
    return claims


async def require_csrf(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """
    Validates CSRF header for state-mutating requests when using Cookie authentication.
    Bearer tokens with custom headers are immune to simple CSWSH/CSRF.
    """
    # If request used Authorization Bearer header, CSRF is inherently mitigated
    if auth_header and auth_header.credentials:
        return True

    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    session_data = verify_session_token(token)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    csrf_header = request.headers.get("X-CSRF-Token")
    expected_csrf = session_data.get("csrf_token")

    if (
        not csrf_header
        or not expected_csrf
        or not hmac.compare_digest(csrf_header, expected_csrf)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token"
        )
    return True
