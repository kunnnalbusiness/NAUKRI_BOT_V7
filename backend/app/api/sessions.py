"""
Sessions Management and Interactive WebSocket Screencast Router.
Includes Session Import/Export feature to bypass cloud datacenter IP restrictions.
"""

import json
import asyncio
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, Body
from fastapi.responses import JSONResponse

from backend.app.core.config import settings
from backend.app.core.security import verify_session_token
from backend.app.core.dependencies import require_auth, require_csrf
from backend.app.services.session_manager import stream_manager
from backend.app.db.mongo import (
    save_encrypted_session,
    get_decrypted_session,
    update_user_settings,
)
from common.login_helper import check_session_status, remove_session, SITES
from common.paths import get_session_path

router = APIRouter(tags=["Sessions"])


@router.get("/sessions")
async def get_sessions_status(claims: Dict[str, str] = Depends(require_auth)):
    """Returns session validity status for Naukri and LinkedIn for the active user."""
    username = claims.get("username", "admin")
    return {
        "naukri": check_session_status(
            "naukri", force_live_check=False, username=username
        ),
        "linkedin": check_session_status(
            "linkedin", force_live_check=False, username=username
        ),
    }


@router.post("/sessions/{site}/check")
async def check_session_now(
    site: str,
    claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Runs on-demand live headless verification scoped to the user."""
    if site not in ("naukri", "linkedin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown site"
        )
    username = claims.get("username", "admin")
    res = await asyncio.to_thread(check_session_status, site, True, username)
    return res


@router.delete("/sessions/{site}")
async def delete_session_route(
    site: str,
    claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Deletes session file and MongoDB backup for the active user."""
    site = site.lower().strip()
    if site not in ("naukri", "linkedin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown site"
        )
    username = claims.get("username", "admin").strip().lower()

    # 1. Stop engine immediately & set status to 'Session removed'
    from common.engine_manager import engine_manager

    engine_manager.stop_engine(site, username=username, is_admin=True)
    engine_manager.mark_session_removed(site, username=username)

    # 2. Close BrowserManager contexts and pages for this user & site
    from backend.app.services.browser_manager import browser_manager

    browser_manager.close_context(username, site)

    # 3. Remove local session file & invalidate in-memory verification cache
    removed = remove_session(site, username=username)

    # 4. Remove session from MongoDB backup
    from backend.app.db.mongo import delete_encrypted_session, log_user_activity

    delete_encrypted_session(username, site)

    # 5. Clear session metadata in DB
    update_user_settings(
        username, session_metadata={site: {"logged_in": False, "last_verified": None}}
    )

    # 6. Audit log entry
    log_user_activity(
        username,
        "session_removed",
        f"{site.title()} session removed",
        ip=claims.get("ip", "127.0.0.1"),
    )

    return {
        "success": True,
        "removed": removed,
        "status": "Session removed",
        "message": f"{site.title()} session removed successfully.",
    }


@router.post("/sessions/cancel")
async def cancel_streaming_session(
    _claims: Dict[str, str] = Depends(require_auth), _csrf: bool = Depends(require_csrf)
):
    """Cancels active remote browser login session."""
    cancelled = await stream_manager.cancel_active()
    return {"success": True, "cancelled": cancelled}


@router.post("/sessions/{site}/import")
async def import_session_route(
    site: str,
    payload: Dict[str, Any] = Body(...),
    claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """
    Imports a valid Playwright storage_state or cookies JSON exported from local residential IP.
    Bypasses datacenter 403 blocks completely and clears any previous daily limit state for this account.
    """
    if site not in ("naukri", "linkedin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown site"
        )

    username = claims.get("username", "admin")
    session_json_str = json.dumps(payload, indent=2)

    # Save to disk
    dest_path = get_session_path(site, username=username)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(session_json_str, encoding="utf-8")

    # Encrypt and back up to MongoDB
    save_encrypted_session(username, site, session_json_str)
    update_user_settings(
        username,
        session_metadata={site: {"logged_in": True, "last_verified": "Imported"}},
    )

    # Reset any previous daily limit lock for this account
    from common.engine_manager import engine_manager

    engine_manager.reset_daily_limit(site, username=username)

    # Quick non-browser structural check (force_live_check=False avoids spawning a
    # real browser that would block in CI / local envs without Playwright binaries).
    status_res = check_session_status(site, False, username)
    return {
        "success": True,
        "message": f"Successfully imported {site.title()} session!",
        "status": status_res,
    }


@router.get("/sessions/{site}/export")
async def export_session_route(
    site: str, claims: Dict[str, str] = Depends(require_auth)
):
    """Exports active session storage state JSON for backup or debugging."""
    if site not in ("naukri", "linkedin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown site"
        )

    username = claims.get("username", "admin")
    dest_path = get_session_path(site, username=username)

    if not dest_path.exists():
        # Check MongoDB
        restored = get_decrypted_session(username, site)
        if restored:
            return JSONResponse(content=json.loads(restored))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No active session found."
        )

    try:
        content = json.loads(dest_path.read_text(encoding="utf-8"))
        return JSONResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read session: {e}")


@router.websocket("/ws/session/{site}")
async def websocket_session_stream(websocket: WebSocket, site: str):
    """
    WebSocket endpoint for interactive CDP browser screencast and input forwarding.
    Enforces authentication, Origin header verification, and query token validation.
    """
    # 1. Authenticate via short-lived single-use ticket, token param, or session cookie
    ticket = websocket.query_params.get("ticket")
    session_data = None
    if ticket:
        from backend.app.core.security import consume_ws_ticket

        session_data = consume_ws_ticket(ticket)

    if not session_data:
        token = websocket.query_params.get("token") or websocket.cookies.get(
            settings.SESSION_COOKIE_NAME
        )
        session_data = verify_session_token(token)

    if not session_data:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Check Origin header against CSWSH
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")
    if origin and host:
        origin_host = origin.split("://")[-1].split("/")[0]
        # Ignore port discrepancies between reverse proxy and origin
        if origin_host.split(":")[0] != host.split(":")[0]:
            # Check if origin in allowed origins list
            allowed = any(origin_host in ao for ao in settings.ALLOWED_ORIGINS)
            if not allowed:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

    if site not in SITES:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return

    mode = websocket.query_params.get("mode", "login")
    username = session_data.get("username", "admin")
    fps_param = websocket.query_params.get("fps")
    target_fps = int(fps_param) if fps_param and fps_param.isdigit() else None

    await websocket.accept()
    await stream_manager.start_streaming(
        site, websocket, mode=mode, username=username, target_fps=target_fps
    )
