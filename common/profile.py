"""Loads and validates the applicant profile dynamically from config/profile.yaml or MongoDB for users."""

from typing import Optional
import yaml
from pathlib import Path

from common.paths import get_config_path, get_resume_path


class Profile:
    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def load(cls, path: str = "profile.yaml") -> "Profile":
        p = get_config_path(path)
        if not p.exists():
            raise FileNotFoundError(
                f"{path} not found in config/ or project root. Please create profile.yaml."
            )
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cls._validate(data)
        return cls(data)

    @classmethod
    def load_for_user(cls, username: Optional[str] = None) -> "Profile":
        """
        Loads profile for a specific user:
        - Admin user: Loads existing config/profile.yaml.
        - Non-admin user: Loads strictly from MongoDB user_profiles collection. Never falls back to config/profile.yaml.
        """
        if not username:
            raise ValueError("Username must be provided to load user profile.")

        u_clean = username.strip().lower()
        from common.db import get_user, get_user_profile, is_user_profile_complete

        user = get_user(u_clean)
        if u_clean == "admin" or (user and user.get("role") == "admin"):
            return cls.load()

        is_complete, reason, _ = is_user_profile_complete(u_clean)
        if not is_complete:
            raise ValueError(f"Pehle profile complete karo: {reason}")

        data = get_user_profile(u_clean)
        if not data:
            raise ValueError(
                f"Pehle profile complete karo: No profile found for '{u_clean}'."
            )

        return cls(data)

    @staticmethod
    def _validate(data: dict):
        required_blocking = [
            "total_experience_years",
            "notice_period_days",
            "current_ctc_lpa",
            "expected_ctc_lpa",
        ]
        missing = [k for k in required_blocking if data.get(k) in (None, "")]
        if not data.get("resume_file_name") and not data.get("resume_path"):
            missing.append("resume_file_name")
        if missing:
            raise ValueError(
                "Pehle profile complete karo: Missing required fields: "
                + ", ".join(missing)
                + ". These gate screening questions — please fill them in."
            )

    def __getattr__(self, item):
        if item in self.data:
            return self.data[item]
        # Safe default values for optional profile attributes
        defaults = {
            "target_roles": ["Software Engineer"],
            "role_required_keywords": {},
            "current_city": "Delhi / NCR",
            "relocate_cities": ["All India", "Remote"],
            "work_mode": "flexible",
            "night_shift_ok": False,
            "weekend_ok": False,
            "total_experience_years": 2,
            "current_employer": "",
            "current_title_official": "",
            "current_title_functional": "",
            "notice_period_days": 30,
            "immediately_available": False,
            "current_ctc_lpa": 5.0,
            "expected_ctc_lpa": 7.0,
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
            "human_input_timeout_seconds": 12,
            "max_pages_per_role": 15,
            "browser_mode": "visible",
            "resume_file_name": "",
            "resume_path": "",
            "full_name": "",
            "email": "",
            "phone": "",
            "date_of_birth": "",
            "gender": "",
            "marital_status": "",
        }
        if item in defaults:
            return defaults[item]
        raise AttributeError(item)

    def get_resolved_resume_path(self) -> Path:
        """Finds the actual resume file path dynamically."""
        # 1. Direct explicit user-uploaded resume path
        custom_path = self.data.get("resume_path")
        if custom_path:
            p = Path(custom_path)
            if p.exists():
                return p

        # 2. Filename resolution via resolver
        resume_name = self.data.get("resume_file_name", "")
        return get_resume_path(resume_name)

    def answer_library(self) -> dict:
        """Common recurring screening-question answers, pre-computed once."""
        d = self.data
        ctc_policy = d.get("ctc_disclosure_policy", "real_numbers")
        curr_ctc = d.get("current_ctc_lpa", "")
        exp_ctc = d.get("expected_ctc_lpa", "")
        return {
            "years_experience": str(d.get("total_experience_years", 0)),
            "notice_period": (
                "Immediately available"
                if d.get("immediately_available")
                else f"{d.get('notice_period_days', 30)} days"
            ),
            "current_ctc": (
                "Prefer to discuss" if ctc_policy == "negotiable" else f"{curr_ctc} LPA"
            ),
            "expected_ctc": (
                "Negotiable" if ctc_policy == "negotiable" else f"{exp_ctc} LPA"
            ),
            "current_city": str(d.get("current_city", "")),
            "relocate": "Yes" if d.get("relocate_cities") else "No",
            "night_shift": "Yes" if d.get("night_shift_ok") else "No",
            "weekend_work": "Yes" if d.get("weekend_ok") else "No",
            "date_of_birth": str(d.get("date_of_birth", "")),
            "gender": str(d.get("gender", "")),
            "marital_status": str(d.get("marital_status", "")),
            "full_name": str(d.get("full_name", "")),
            "phone": str(d.get("phone", "")),
            "email": str(d.get("email", "")),
        }
