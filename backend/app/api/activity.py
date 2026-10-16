"""
Live Application Activity API Router.
Returns real-time job application feed, counters, and statistics scoped by user.
"""

from typing import Dict
from fastapi import APIRouter, Depends

from backend.app.core.dependencies import require_auth, require_csrf
from common.engine_manager import engine_manager
from common import google_sheet

router = APIRouter(prefix="/activity", tags=["Application Activity"])


@router.get("")
async def get_activity_feed(claims: Dict[str, str] = Depends(require_auth)):
    """Returns detailed application logs and engine state for the user."""
    username = claims.get("username", "admin")
    activity = google_sheet.get_application_activity(limit=100, username=username)
    activity["engines"] = engine_manager.get_status(username=username)
    return activity


@router.post("/clear")
async def clear_activity_route(
    claims: Dict[str, str] = Depends(require_auth), _csrf: bool = Depends(require_csrf)
):
    """Clears live application history feed for the authenticated user."""
    username = claims.get("username", "admin")
    google_sheet.clear_application_activity(username=username)
    return {"success": True, "message": "Live activity feed cleared."}
