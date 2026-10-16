"""
Admin System Monitor API Router.
Exposes container-aware resource stats, an SSE live stream, and manual
incident notes. Strictly restricted to the admin role.
"""

import asyncio
import json
import time
from typing import Dict

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.app.core.dependencies import require_admin, require_csrf
from backend.app.core.preflight import run_browser_preflight
from backend.app.services import system_stats, uptime_service

router = APIRouter(tags=["System Monitor"])


@router.get("/system/health")
async def system_health_endpoint(
    deep: int = Query(0, description="Set to 1 to run on-demand Chromium launch test"),
    _claims: Dict[str, str] = Depends(require_admin),
):
    """
    Admin only: system health and runtime preflight status.
    When ?deep=1, executes a real headless Chromium launch test (about:blank) on demand.
    """
    preflight_info = run_browser_preflight()

    if deep == 1:
        t0 = time.perf_counter()
        from backend.app.services.browser_manager import browser_manager

        check_res = await asyncio.to_thread(browser_manager.deep_health_check)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if check_res.get("status") == "ok":
            return {
                "status": "healthy",
                "deep": True,
                "browser_launch": {
                    "success": True,
                    "latency_ms": latency_ms,
                    "pid": check_res.get("browser_pid"),
                },
                "preflight": {
                    "ok": preflight_info.ok,
                    "error_code": preflight_info.error_code,
                    "message": preflight_info.message,
                    "executable_path": preflight_info.executable_path,
                },
            }
        else:
            # Return 200 with degraded status — HTTP 5xx would mask the details
            # from health checkers; callers must inspect browser_launch.success.
            return JSONResponse(
                status_code=200,
                content={
                    "status": "degraded",
                    "deep": True,
                    "browser_launch": {
                        "success": False,
                        "error": check_res.get("error"),
                        "latency_ms": latency_ms,
                    },
                    "preflight": {
                        "ok": False,
                        "error_code": "BROWSER_LAUNCH_FAILED",
                        "message": check_res.get("error"),
                        "admin_hint": "Check container /dev/shm size or missing system libraries.",
                    },
                },
            )

    return {
        "status": "ok",
        "deep": False,
        "preflight": {
            "ok": preflight_info.ok,
            "error_code": preflight_info.error_code,
            "message": preflight_info.message,
            "executable_path": preflight_info.executable_path,
        },
    }


@router.get("/system/storage-health")
async def storage_health_endpoint(_claims: Dict[str, str] = Depends(require_admin)):
    """
    Admin only: storage health diagnostics.
    Tests MongoDB ping, write/read/delete round-trip, and encryption/decryption round-trip.
    """
    from backend.app.db.mongo import check_storage_health

    health_res = await asyncio.to_thread(check_storage_health)
    status_code = 200 if health_res.get("status") == "ok" else 500
    return JSONResponse(status_code=status_code, content=health_res)


@router.get("/system/metrics")
async def get_system_metrics(_claims: Dict[str, str] = Depends(require_admin)):
    """
    Admin only: snapshot telemetry from BrowserManager and MemoryWatchdog.
    Returns memory %, browser tree RSS, uptime, active contexts, and watchdog tier.
    """
    from backend.app.services.browser_manager import browser_manager

    return browser_manager.get_metrics()


class IncidentNoteRequest(BaseModel):
    component: str = Field("api", max_length=40)
    note: str = Field(..., min_length=1, max_length=500)


@router.get("/admin/system/stats")
async def get_system_stats(_claims: Dict[str, str] = Depends(require_admin)):
    """Admin only: one-shot system stats snapshot (CPU, memory, disk, workers, DB)."""
    return await asyncio.to_thread(system_stats.collect_stats)


@router.get("/admin/system/stats/stream")
async def stream_system_stats(
    request: Request, _claims: Dict[str, str] = Depends(require_admin)
):
    """
    Admin only: Server-Sent Events stream pushing stats every 2 seconds.
    Stops when the client disconnects.
    """

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                stats = await asyncio.to_thread(system_stats.collect_stats)
                payload = json.dumps(stats, default=str)
                yield f"data: {payload}\n\n"
            except Exception:
                yield f"event: error\ndata: {json.dumps({'detail': 'stats collection failed'})}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/admin/system/history")
async def get_stats_history(_claims: Dict[str, str] = Depends(require_admin)):
    """Admin only: 15-minute rolling sparkline history (5 s resolution)."""
    return {"history": system_stats.get_history()}


@router.post("/admin/system/incidents")
async def add_incident_note(
    body: IncidentNoteRequest,
    claims: Dict[str, str] = Depends(require_admin),
    _csrf: bool = Depends(require_csrf),
):
    """Admin only: posts a manual incident note shown on the public status page."""
    incident = uptime_service.add_manual_note(
        component=body.component,
        note=body.note,
        author=claims.get("username", "admin"),
    )
    incident.pop("_id", None)
    return {"success": True, "incident": incident}
