"""
Job Seeker Profile and Resume Models.
"""

from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class ProfileUpdateRequest(BaseModel):
    # Personal & Location
    full_name: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    current_city: Optional[str] = ""
    relocate_cities: Optional[List[str]] = []
    work_mode: Optional[str] = "flexible"
    night_shift_ok: Optional[bool] = False
    weekend_ok: Optional[bool] = False
    date_of_birth: Optional[str] = ""
    gender: Optional[str] = ""
    marital_status: Optional[str] = ""

    # Roles & Skills
    target_roles: Optional[List[str]] = []
    role_required_keywords: Optional[Dict[str, List[str]]] = {}
    total_experience_years: Optional[float] = 0
    current_employer: Optional[str] = ""
    current_title_official: Optional[str] = ""
    current_title_functional: Optional[str] = ""
    highest_qualification: Optional[str] = ""
    certifications: Optional[List[str]] = []
    skills_primary: Optional[List[str]] = []
    skills_adjacent: Optional[List[str]] = []
    work_history_narrative: Optional[str] = ""

    # Compensation & Notice
    notice_period_days: Optional[int] = 30
    immediately_available: Optional[bool] = False
    current_ctc_lpa: Optional[float] = 0
    expected_ctc_lpa: Optional[float] = 0
    ctc_disclosure_policy: Optional[str] = "real_numbers"

    # Search & Filtering Preferences
    company_exclude: Optional[List[str]] = []
    company_include_only: Optional[List[str]] = []
    seniority_floor_years: Optional[int] = 0
    seniority_ceiling_years: Optional[int] = 5
    job_freshness_days: Optional[int] = 15
    salary_floor_lpa: Optional[float] = None
    stop_after_n_applications: Optional[int] = 2000
    pace_seconds_between_actions: Optional[int] = Field(5, ge=2, le=120)
    max_pages_per_role: Optional[int] = 15

    # Resume metadata
    resume_path: Optional[str] = ""
    resume_file_name: Optional[str] = ""
