"""
Public Status Page API Router.
No authentication, no sensitive data: only aggregate component uptime,
banner state, and incident history. Note: this must never include user
data, hostnames, or stack traces.
"""

from fastapi import APIRouter

from backend.app.services import uptime_service

router = APIRouter(prefix="/status", tags=["Public Status"])


@router.get("/summary")
async def get_public_status():
    """Public: overall banner, per-component uptime (24h/7d/30d/90d), 90-day bars, incidents."""
    return uptime_service.get_status_summary()
