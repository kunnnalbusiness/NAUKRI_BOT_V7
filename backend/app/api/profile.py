"""
User Profile and Resume Management API Router.
Handles all 5 profile sections, completeness verification, and secure PDF upload/preview.
"""

from typing import Dict
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException

from backend.app.core.dependencies import require_auth, require_csrf
from backend.app.db.mongo import (
    get_user_profile,
    save_user_profile,
    is_user_profile_complete,
)
from backend.app.models.profile import ProfileUpdateRequest
from backend.app.services.resume_service import (
    handle_resume_upload,
    get_resume_download,
)

router = APIRouter(prefix="/profile", tags=["User Profile"])


@router.get("")
async def get_profile_route(claims: Dict[str, str] = Depends(require_auth)):
    """Returns profile data and completeness report for the authenticated user."""
    username = claims.get("username", "admin").strip().lower()
    role = claims.get("role", "user")

    if role == "admin":
        from common.profile import Profile

        try:
            p = Profile.load()
            data = dict(p.data)
            data["is_admin"] = True
            data["username"] = "admin"
            data["is_complete"] = True
            data["completeness_reason"] = ""
            data["missing_fields"] = []
            return data
        except Exception:
            pass

    data = get_user_profile(username)
    if not data:
        data = {
            "username": username,
            "full_name": "",
            "email": "",
            "phone": "",
            "current_city": "",
            "relocate_cities": ["All India", "Remote"],
            "work_mode": "flexible",
            "night_shift_ok": False,
            "weekend_ok": False,
            "date_of_birth": "",
            "gender": "",
            "marital_status": "",
            "target_roles": [],
            "role_required_keywords": {},
            "total_experience_years": None,
            "current_employer": "",
            "current_title_official": "",
            "current_title_functional": "",
            "notice_period_days": 30,
            "immediately_available": False,
            "current_ctc_lpa": None,
            "expected_ctc_lpa": None,
            "ctc_disclosure_policy": "real_numbers",
            "highest_qualification": "",
            "certifications": [],
            "skills_primary": [],
            "skills_adjacent": [],
            "work_history_narrative": "",
            "company_exclude": [],
            "company_include_only": [],
            "seniority_floor_years": 0,
            "seniority_ceiling_years": 5,
            "job_freshness_days": 15,
            "salary_floor_lpa": None,
            "stop_after_n_applications": 2000,
            "pace_seconds_between_actions": 5,
            "max_pages_per_role": 15,
            "resume_file_name": "",
            "resume_path": "",
            "resume_size_bytes": 0,
            "resume_uploaded_at": "",
        }

    is_complete, reason, missing = is_user_profile_complete(username)
    data["is_complete"] = is_complete
    data["completeness_reason"] = reason
    data["missing_fields"] = missing
    data["is_admin"] = role == "admin"
    return data


@router.post("")
async def save_profile_route(
    body: ProfileUpdateRequest,
    claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Saves updated profile data for the authenticated user."""
    username = claims.get("username", "admin").strip().lower()

    existing = get_user_profile(username) or {}
    new_data = body.model_dump()

    # Retain existing resume metadata if not passed
    if not new_data.get("resume_path") and existing.get("resume_path"):
        new_data["resume_path"] = existing["resume_path"]
        new_data["resume_file_name"] = existing.get("resume_file_name", "")
        new_data["resume_size_bytes"] = existing.get("resume_size_bytes", 0)
        new_data["resume_uploaded_at"] = existing.get("resume_uploaded_at", "")

    ok = save_user_profile(username, new_data)
    if not ok:
        raise HTTPException(
            status_code=500, detail="Failed to save profile to database."
        )

    is_complete, reason, missing = is_user_profile_complete(username)
    return {
        "success": True,
        "message": "Profile saved successfully.",
        "is_complete": is_complete,
        "missing_fields": missing,
        "completeness_reason": reason,
    }


@router.post("/resume")
async def upload_resume_route(
    file: UploadFile = File(...),
    claims: Dict[str, str] = Depends(require_auth),
    _csrf: bool = Depends(require_csrf),
):
    """Uploads resume PDF (max 5MB) for the authenticated user."""
    username = claims.get("username", "admin").strip().lower()
    return await handle_resume_upload(file, username)


@router.get("/resume/download")
async def download_resume_route(claims: Dict[str, str] = Depends(require_auth)):
    """Downloads or previews the authenticated user's uploaded resume PDF."""
    username = claims.get("username", "admin").strip().lower()
    return get_resume_download(username)
