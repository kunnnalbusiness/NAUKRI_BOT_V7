"""
Automation Engine Controls and AI Key Rotator Router.
"""

from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request

from backend.app.core.dependencies import require_auth, require_admin, require_csrf
from backend.app.db.mongo import (
    get_user_settings,
    is_user_profile_complete,
    update_user_settings,
)
from backend.app.models.bot import AddKeyRequest, UpdateKeyRequest
from common.engine_manager import engine_manager
from common.login_helper import check_session_status
from common.key_rotator import key_rotator
from common import google_sheet

router = APIRouter(tags=["Bot Engines & Keys"])


@router.get("/status")
async def get_dashboard_status(claims: Dict[str, str] = Depends(require_auth)):
    """Returns aggregated status of engines, sessions, AI keys, user settings, and activity scoped by user."""
    username = claims.get("username", "admin")
    role = claims.get("role", "user")

    engines_state = engine_manager.get_status(username=username)

    # Scoped session statuses
    naukri_session = check_session_status(
        "naukri", force_live_check=False, username=username
    )
    linkedin_session = check_session_status(
        "linkedin", force_live_check=False, username=username
    )

    user_settings = get_user_settings(username)

    # Sheet settings
    sheet_cfg = user_settings.get("sheet_config", {})
    if role == "admin":
        sheet_url = sheet_cfg.get("sheet_url") or google_sheet.get_sheet_url_and_id()[0]
        webhook_url = sheet_cfg.get("webhook_url") or google_sheet.get_webhook_url()
    else:
        sheet_url = sheet_cfg.get("sheet_url") or ""
        webhook_url = sheet_cfg.get("webhook_url") or ""

    # Keys status: admin sees configured keys, standard users see blank
    if role == "admin":
        llm_status = key_rotator.get_status()
    else:
        llm_status = {
            "keys": [],
            "current_key": None,
            "quota_status": "No keys configured",
            "active_provider": None,
        }

    activity = google_sheet.get_application_activity(limit=100, username=username)

    # Daily Limit Status
    n_limit = engines_state.get("naukri", {}).get("daily_limit_exceeded", False)
    l_limit = engines_state.get("linkedin", {}).get("daily_limit_exceeded", False)
    any_limit = n_limit or l_limit
    limit_reason = ""
    if n_limit and l_limit:
        limit_reason = "Daily quota reached on both Naukri and LinkedIn. Resets automatically at 12:00 AM."
    elif n_limit:
        limit_reason = (
            "Naukri daily application quota reached (50-80 jobs). Resets at 12:00 AM."
        )
    elif l_limit:
        limit_reason = "LinkedIn daily Easy Apply limit reached. Resets at 12:00 AM."

    if role == "admin":
        profile_meta = {"is_complete": True, "reason": "", "missing": []}
    else:
        p_complete, p_reason, p_missing = is_user_profile_complete(username)
        profile_meta = {
            "is_complete": p_complete,
            "reason": p_reason,
            "missing": p_missing,
        }

    return {
        "user": {
            "username": username,
            "role": role,
            "delay_seconds": user_settings.get("delay_seconds", 5),
            "is_admin": role == "admin",
            "total_applied": user_settings.get("total_applied", 0),
        },
        "profile": profile_meta,
        "engines": engines_state,
        "daily_limit": {
            "exceeded": any_limit,
            "naukri_exceeded": n_limit,
            "linkedin_exceeded": l_limit,
            "reason": limit_reason,
            "reset_time": "12:00 AM",
        },
        "sessions": {"naukri": naukri_session, "linkedin": linkedin_session},
        "sheet": {
            "sheet_url": sheet_url,
            "webhook_url": webhook_url,
            "webhook_configured": bool(webhook_url),
            "is_optional": True,
        },
        "llm": llm_status,
        "activity": activity,
        "csrf_token": claims.get("csrf_token"),
    }


@router.post("/engine/{site}/start")
@router.post("/bot/{site}/start")
async def start_engine_route(
    site: str,
    request: Request,
    claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Starts background automation engine for site scoped to authenticated user."""
    username = claims.get("username", "admin")
    role = claims.get("role", "user")

    only_fresh_10min = False
    only_fresh = None
    fresh_threshold_minutes = None
    try:
        body = await request.json()
        only_fresh_10min = bool(body.get("only_fresh_10min", False))
        if "only_fresh" in body:
            only_fresh = bool(body["only_fresh"])
        thresh_raw = body.get("fresh_threshold_minutes") or body.get(
            "threshold_minutes"
        )
        if thresh_raw is not None:
            fresh_threshold_minutes = max(1, int(thresh_raw))
    except Exception:
        pass

    # Profile completeness check for non-admin users
    if role != "admin":
        complete, p_reason, _ = is_user_profile_complete(username)
        if not complete:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Pehle profile complete karo: {p_reason}",
            )

    success, msg = engine_manager.start_engine(
        site,
        username=username,
        only_fresh_10min=only_fresh_10min,
        only_fresh=only_fresh,
        fresh_threshold_minutes=fresh_threshold_minutes,
    )
    if not success:
        if "busy" in msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.post("/engine/{site}/stop")
@router.post("/bot/{site}/stop")
async def stop_engine_route(
    site: str,
    claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Stops background automation engine for site."""
    username = claims.get("username", "")
    is_admin = claims.get("role") == "admin"
    success, msg = engine_manager.stop_engine(
        site, username=username, is_admin=is_admin
    )
    if not success:
        if "permission" in msg.lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"success": True, "message": msg}


@router.post("/engine/all/stop")
@router.post("/bot/all/stop")
async def stop_all_engines_route(
    claims: Dict[str, str] = Depends(require_auth), _csrf: bool = Depends(require_csrf)
):
    """Stops all running automation engines simultaneously."""
    username = claims.get("username", "")
    is_admin = claims.get("role") == "admin"
    engine_manager.stop_engine("naukri", username=username, is_admin=is_admin)
    engine_manager.stop_engine("linkedin", username=username, is_admin=is_admin)
    return {"success": True, "message": "All automation engines stopped."}


@router.post("/engine/{site}/reset-limit")
@router.post("/bot/{site}/reset-limit")
async def reset_daily_limit_route(
    site: str,
    _claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Resets daily limit flag for site."""
    engine_manager.reset_daily_limit(site)
    return {"success": True, "message": f"{site.title()} daily limit cleared."}


@router.post("/engine/{site}/fresh-filter")
@router.post("/bot/{site}/fresh-filter")
async def set_fresh_filter_route(
    site: str,
    request: Request,
    _claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Configures the dynamic fresh jobs filter threshold (number + minutes/hours)."""
    if site not in ("naukri", "linkedin"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Invalid site '{site}'."
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    current_st = engine_manager.get_engine_state(site)

    # Resolve enabled
    enabled = body.get("enabled")
    if enabled is None:
        if "only_fresh" in body:
            enabled = bool(body["only_fresh"])
        elif "only_fresh_10min" in body:
            enabled = bool(body["only_fresh_10min"])
        else:
            # Toggle current setting
            enabled = not current_st.get(
                "only_fresh", current_st.get("only_fresh_10min", False)
            )
    else:
        enabled = bool(enabled)

    # Resolve threshold minutes
    thresh_val = body.get("threshold_minutes") or body.get("fresh_threshold_minutes")
    if thresh_val is None:
        thresh_val = current_st.get("fresh_threshold_minutes", 10)

    try:
        thresh_minutes = max(1, int(thresh_val))
    except (ValueError, TypeError):
        thresh_minutes = 10

    success, updated_state = engine_manager.set_fresh_filter(
        site, enabled=enabled, threshold_minutes=thresh_minutes
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not update {site} fresh filter.",
        )

    return {
        "success": True,
        "site": site,
        "enabled": enabled,
        "threshold_minutes": thresh_minutes,
        "only_fresh": enabled,
        "only_fresh_10min": enabled,
        "fresh_threshold_minutes": thresh_minutes,
    }


@router.post("/engine/{site}/pacing")
@router.post("/bot/{site}/pacing")
async def set_pacing_route(
    site: str,
    request: Request,
    claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Configures dynamic per-card scanning pace (in seconds) for continuous execution."""
    if site not in ("naukri", "linkedin"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Invalid site '{site}'."
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    pace_val = body.get("pace_seconds") or body.get("delay_seconds")
    if pace_val is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="pace_seconds is required."
        )

    try:
        pace_seconds = max(1.0, min(120.0, float(pace_val)))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pace_seconds number.",
        )

    success, updated_state = engine_manager.set_pacing(site, pace_seconds)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not update {site} pacing.",
        )

    # Persist in user settings as well
    username = claims.get("username")
    if username:
        try:
            update_user_settings(
                username, delay_seconds=max(2, int(round(pace_seconds)))
            )
        except Exception:
            pass

    return {
        "success": True,
        "site": site,
        "pace_seconds": pace_seconds,
        "engine": updated_state,
    }


@router.post("/engine/{site}/toggle-fresh-10min")
@router.post("/bot/{site}/toggle-fresh-10min")
async def toggle_fresh_10min_route(
    site: str,
    _claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Backward compatible toggle endpoint for fresh jobs filter."""
    if site not in ("naukri", "linkedin"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Invalid site '{site}'."
        )
    current_st = engine_manager.get_engine_state(site)
    new_enabled = not current_st.get(
        "only_fresh", current_st.get("only_fresh_10min", False)
    )
    thresh = int(current_st.get("fresh_threshold_minutes", 10))
    engine_manager.set_fresh_filter(site, enabled=new_enabled, threshold_minutes=thresh)
    return {
        "success": True,
        "site": site,
        "only_fresh_10min": new_enabled,
        "only_fresh": new_enabled,
        "fresh_threshold_minutes": thresh,
    }


@router.post("/engine/reset-limit")
async def api_reset_daily_limit(
    site: Optional[str] = None,
    _claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Resets daily quota limit status."""
    engine_manager.reset_daily_limit(site)
    return {"success": True, "message": "Daily limit status reset."}


# Keys Management (admin only: provider keys are shared infrastructure)
@router.get("/keys")
async def get_keys_route(_claims: Dict[str, str] = Depends(require_admin)):
    """Returns masked list of configured AI provider keys."""
    return key_rotator.get_masked_keys()


@router.post("/keys")
async def add_key_route(
    body: AddKeyRequest,
    _claims: Dict[str, str] = Depends(require_admin),
    _csrf: bool = Depends(require_csrf),
):
    """Adds a new Gemini or Groq API key."""
    if not body.key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="API key cannot be empty."
        )
    if body.provider.lower() not in ("gemini", "groq"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider must be 'gemini' or 'groq'.",
        )

    key_id = key_rotator.add_key(
        body.provider.lower(), body.key.strip(), enabled=body.enabled
    )
    return {"success": True, "key_id": key_id}


@router.put("/keys/{key_id}")
async def update_key_route(
    key_id: str,
    body: UpdateKeyRequest,
    _claims: Dict[str, str] = Depends(require_admin),
    _csrf: bool = Depends(require_csrf),
):
    """Enables or disables an API key."""
    ok = key_rotator.update_key(key_id, enabled=body.enabled)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Key ID not found."
        )
    return {"success": True}


@router.delete("/keys/{key_id}")
async def delete_key_route(
    key_id: str,
    _claims: Dict[str, str] = Depends(require_admin),
    _csrf: bool = Depends(require_csrf),
):
    """Removes an API key."""
    ok = key_rotator.remove_key(key_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Key ID not found."
        )
    return {"success": True}


@router.post("/keys/{key_id}/test")
async def test_key_route(
    key_id: str,
    _claims: Dict[str, str] = Depends(require_admin),
    _csrf: bool = Depends(require_csrf),
):
    """Tests an API key validity with a lightweight test call."""
    return key_rotator.test_key(key_id)
