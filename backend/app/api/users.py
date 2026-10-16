"""
User Settings API Router.
Controls custom delay (min safe 2s) and user-specific Google Sheets sync.
"""

from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.dependencies import require_auth, require_csrf
from backend.app.db.mongo import get_user_settings, update_user_settings
from backend.app.models.user import UserSettingsUpdate, UserSettingsOut

router = APIRouter(prefix="/user", tags=["User Settings"])


@router.get("/settings", response_model=UserSettingsOut)
async def get_settings_route(claims: Dict[str, str] = Depends(require_auth)):
    """Retrieves authenticated user's current settings."""
    username = claims.get("username", "admin")
    return get_user_settings(username)


@router.post("/settings")
async def update_settings_route(
    body: UserSettingsUpdate,
    claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Updates user-specific custom application delay (min 2s), stream FPS, and sheet sync."""
    username = claims.get("username", "admin")
    delay = max(2, int(body.delay_seconds)) if body.delay_seconds is not None else None
    fps = max(1, min(60, int(body.stream_fps))) if body.stream_fps is not None else None

    sheet_cfg = {}
    if body.webhook_url is not None:
        sheet_cfg["webhook_url"] = body.webhook_url.strip()
    if body.sheet_url is not None:
        sheet_cfg["sheet_url"] = body.sheet_url.strip()

    ok = update_user_settings(
        username,
        delay_seconds=delay,
        stream_fps=fps,
        sheet_config=sheet_cfg if sheet_cfg else None,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings.",
        )

    msg_parts = []
    if delay is not None:
        msg_parts.append(f"Application delay: {delay}s")
    if fps is not None:
        msg_parts.append(f"Stream rate: {fps} FPS")
    msg_str = ", ".join(msg_parts) if msg_parts else "Settings updated"

    return {"success": True, "message": f"Settings saved. {msg_str}."}
