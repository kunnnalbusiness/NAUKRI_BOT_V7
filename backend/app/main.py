"""
FastAPI Main Application Entrypoint.
Production-grade setup with CORS, security headers, reverse proxy header awareness,
health check endpoints, and mounted routers.
"""

import os
import uuid
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.app.core.config import settings, PROJECT_ROOT

# Side-effect import: loading this module installs the secrets-sanitizing log handler
from backend.app.core.logging import setup_logging  # noqa: F401
from backend.app.services.session_manager import stream_manager
from backend.app.services import system_stats, uptime_service
from common.engine_manager import engine_manager
import logging

logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Autonomous Job Apply Automation Backend...")
    warnings = settings.validate_setup()
    for w in warnings:
        logger.warning(f"[Config Warning] {w}")

    # Lightweight browser preflight check (does not launch browser process)
    try:
        from backend.app.core.preflight import run_browser_preflight

        pf = await asyncio.to_thread(run_browser_preflight)
        if pf.ok:
            logger.info(
                f"[Preflight OK] Playwright and Chromium executable verified: {pf.executable_path}"
            )
        else:
            logger.error(f"[Preflight ERROR] {pf.error_code}: {pf.message}")
            logger.error(f"[Preflight Admin Hint] {pf.admin_hint}")
    except Exception as e:
        logger.warning(f"Browser preflight exception: {e}")

    # Storage self-check (non-blocking diagnostic log)
    async def _async_storage_check():
        try:
            from backend.app.db.mongo import check_storage_health

            sh = await asyncio.to_thread(check_storage_health)
            if sh.get("status") == "ok":
                logger.info(
                    f"[Storage Self-Check OK] {sh.get('storage_type')} | ping={sh.get('ping_ms')}ms | db_rt={sh.get('db_roundtrip_ms')}ms | crypto_rt={sh.get('crypto_roundtrip_ms')}ms"
                )
            else:
                logger.warning(
                    f"[Storage Self-Check Warning] Status={sh.get('status')}: {sh}"
                )
        except Exception as se:
            logger.warning(f"Storage self-check exception: {se}")

    asyncio.create_task(_async_storage_check())

    # No auto-resume on restart: engines must strictly start STOPPED
    logger.info("All engines STOPPED (no auto-resume)")

    # Start uptime heartbeat (60 s) and stats history sampler (5 s)
    try:
        uptime_service.start_heartbeat()
    except Exception as e:
        logger.warning(f"Uptime heartbeat did not start: {e}")
    try:
        system_stats.start_history_sampler()
    except Exception as e:
        logger.warning(f"Stats history sampler did not start: {e}")

    yield

    logger.info("Shutting down Automation Backend...")
    system_stats.stop_history_sampler()
    uptime_service.stop_heartbeat()
    try:
        engine_manager.shutdown_all()
    except Exception:
        pass
    try:
        await stream_manager.cancel_active()
    except Exception:
        pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

from starlette.middleware.gzip import GZipMiddleware

# GZip compression for faster responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS: strictly allow configured frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Adds helmet-style security headers and ensures secure cookie transport."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Correlates every request with an X-Request-ID (client-supplied IDs are reused)."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Health Checks (Render & Monitoring)
# ---------------------------------------------------------------------------


@app.get("/healthz", tags=["System Health"])
@app.get("/health", tags=["System Health"])
async def health_check():
    """Unauthenticated health check for Render container deployment & cold starts.
    Deliberately cheap: no DB call, so an external pinger (UptimeRobot, 5 min
    interval) can hit it to keep the Render free instance warm."""
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "timestamp": datetime.now().isoformat(),
        "database": "connected" if os.environ.get("MONGODB_URI") else "local_store",
    }


@app.get("/readyz", tags=["System Health"])
async def readiness_check():
    """Readiness probe: verifies MongoDB connectivity (or local store fallback).
    Returns 503 when the primary datastore is unreachable in production."""
    try:
        from backend.app.db.mongo import get_db

        db = get_db()
        if db is None:
            if settings.ENV == "production":
                return JSONResponse(
                    status_code=503,
                    content={"status": "unready", "database": "unavailable"},
                )
            return {
                "status": "ready",
                "database": "local_store",
                "timestamp": datetime.now().isoformat(),
            }
        db.command("ping")
        return {
            "status": "ready",
            "database": "connected",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception:
        if settings.ENV == "production":
            return JSONResponse(
                status_code=503,
                content={"status": "unready", "database": "unavailable"},
            )
        return {
            "status": "degraded",
            "database": "local_store",
            "timestamp": datetime.now().isoformat(),
        }


# ---------------------------------------------------------------------------
# Include API Routers under /api
# ---------------------------------------------------------------------------

from backend.app.api.auth import router as auth_router
from backend.app.api.users import router as users_router
from backend.app.api.profile import router as profile_router
from backend.app.api.bot import router as bot_router
from backend.app.api.sessions import router as sessions_router
from backend.app.api.activity import router as activity_router
from backend.app.api.admin import router as admin_router
from backend.app.api.sheets import router as sheets_router
from backend.app.api.system import router as system_router
from backend.app.api.status import router as status_router

app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(users_router, prefix=settings.API_V1_PREFIX)
app.include_router(profile_router, prefix=settings.API_V1_PREFIX)
app.include_router(bot_router, prefix=settings.API_V1_PREFIX)
app.include_router(sessions_router, prefix=settings.API_V1_PREFIX)
app.include_router(activity_router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(sheets_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)
app.include_router(status_router, prefix=settings.API_V1_PREFIX)

# Also expose WebSocket at root /ws/session/{site} for direct compatibility
app.include_router(sessions_router)


# ---------------------------------------------------------------------------
# Serve Frontend Single Page App (SPA) when built (production)
# ---------------------------------------------------------------------------

frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    app.mount(
        "/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets"
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Don't hijack API or documentation routes
        if (
            full_path.startswith("api/")
            or full_path.startswith("ws/")
            or full_path in ("docs", "redoc", "openapi.json")
        ):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        file_candidate = frontend_dist / full_path
        if file_candidate.is_file():
            return FileResponse(str(file_candidate))

        return FileResponse(str(frontend_dist / "index.html"))
