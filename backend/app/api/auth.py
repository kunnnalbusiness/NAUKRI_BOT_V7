"""
Authentication API Router.
Handles login, logout, current user verification, rate limiting, and dual Bearer/Cookie token issuance.
"""

import hmac
import os
from typing import Dict
from fastapi import APIRouter, Request, Response, HTTPException, status, Depends

from backend.app.core.config import settings
from backend.app.core.security import (
    check_rate_limit,
    record_failed_attempt,
    reset_failed_attempts,
    verify_password,
    create_session_token,
    create_ws_ticket,
)
from backend.app.core.dependencies import require_auth
from backend.app.db.mongo import get_user
from backend.app.models.user import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/ws-ticket")
async def api_create_ws_ticket(claims: Dict[str, str] = Depends(require_auth)):
    """Issues a short-lived (60s) single-use ticket for WebSocket authentication."""
    ticket = create_ws_ticket(
        claims.get("username", "admin"), claims.get("role", "user")
    )
    return {"ticket": ticket}


@router.post("/login", response_model=LoginResponse)
async def api_login(request: Request, body: LoginRequest, response: Response):
    """
    Authenticates user against MongoDB/env, enforces rate limiting,
    and returns session token in body AND sets HttpOnly cookie.
    """
    client_ip = request.client.host if request.client else "unknown"

    # Enforce rate limit
    allowed, rate_err = check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=rate_err
        )

    u_clean = (body.username or "admin").strip().lower()
    p_clean = body.password.strip()

    user_doc = get_user(u_clean)
    authenticated = False
    role = "user"

    if user_doc:
        if verify_password(p_clean, user_doc.get("password_hash", "")):
            authenticated = True
            role = user_doc.get("role", "user")
    elif u_clean == settings.ADMIN_USERNAME:
        # Fallback if admin doc has not been seeded yet
        if settings.ADMIN_PASSWORD and hmac.compare_digest(p_clean, settings.ADMIN_PASSWORD):
            authenticated = True
            role = "admin"

    if not authenticated:
        record_failed_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    # Success: reset failed attempts
    reset_failed_attempts(client_ip)

    token_version = int(user_doc.get("token_version", 1)) if user_doc else 1
    token, csrf_token = create_session_token(
        username=u_clean, role=role, token_version=token_version
    )

    # Dual-mode cookie setting with production proxy awareness
    is_secure = request.url.scheme == "https" or os.environ.get("RENDER") is not None
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
    )

    return LoginResponse(
        success=True, token=token, csrf_token=csrf_token, username=u_clean, role=role
    )


@router.post("/logout")
async def api_logout(response: Response):
    """Clears authentication session cookie."""
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")
    return {"success": True, "message": "Successfully logged out."}


@router.get("/me")
async def api_me(claims: Dict[str, str] = Depends(require_auth)):
    """Returns claims of the currently authenticated user."""
    return {
        "username": claims.get("username"),
        "role": claims.get("role"),
        "is_admin": claims.get("role") == "admin",
        "csrf_token": claims.get("csrf_token"),
    }
