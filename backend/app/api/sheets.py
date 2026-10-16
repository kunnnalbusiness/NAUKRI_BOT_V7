"""
Google Sheets Integration API Router.
"""

from typing import Dict
from fastapi import APIRouter, Depends

from backend.app.core.dependencies import require_auth, require_csrf
from backend.app.models.bot import SheetSettingsRequest
from backend.app.db.mongo import update_user_settings
from common.runtime_config import set_config_value
from common import google_sheet

router = APIRouter(prefix="/sheet", tags=["Google Sheets"])


@router.post("")
async def update_sheet_settings(
    body: SheetSettingsRequest,
    claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Updates Google Sheet spreadsheet and webhook URLs live."""
    username = claims.get("username", "admin")
    sheet_cfg = {}
    if body.webhook_url.strip():
        sheet_cfg["webhook_url"] = body.webhook_url.strip()
        set_config_value("GOOGLE_SHEET_WEBHOOK_URL", body.webhook_url.strip())
    if body.sheet_url.strip():
        sheet_cfg["sheet_url"] = body.sheet_url.strip()
        set_config_value("GOOGLE_SHEET_URL", body.sheet_url.strip())
    if sheet_cfg:
        update_user_settings(username, sheet_config=sheet_cfg)
    return {"success": True, "message": "Google Sheet configuration saved."}


@router.post("/test")
async def test_sheet_connection(
    _claims: Dict[str, str] = Depends(require_auth), _csrf: bool = Depends(require_csrf)
):
    """Sends a sample test row to verify Google Sheet Webhook connectivity."""
    success, message = google_sheet.send_test_row()
    return {"success": success, "message": message}
