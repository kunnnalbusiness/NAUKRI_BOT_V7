"""
Application Configuration and Environment Settings.
"""

import os
import sys
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Ensure PROJECT_ROOT and backend directory are in sys.path
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Load environment variables from .env if present
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(dotenv_path=env_file)
else:
    load_dotenv()


class Settings:
    PROJECT_NAME: str = "Naukri & LinkedIn Autonomous Job Apply Hub"
    VERSION: str = "2.0.0"
    API_V1_PREFIX: str = "/api"
    # Environment & Deployment Mode
    ENV: str = os.getenv("ENV", "local").lower().strip()

    # Security & Tokens
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "prod-secret-key-naukri-apply-bot-v8-secure-entropy-32chars"
    ).strip()
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "").strip()
    SESSION_COOKIE_NAME: str = "naukri_dashboard_session"
    SESSION_MAX_AGE_SECONDS: int = 7 * 24 * 3600  # 7 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Fresh Jobs Rule (Minutes)
    POSTED_WITHIN_MINUTES: int = int(os.getenv("POSTED_WITHIN_MINUTES", "10"))

    # Admin Credentials
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
    ADMIN_PASSWORD: str = os.getenv(
        "ADMIN_PASSWORD", os.getenv("DASHBOARD_PASSWORD", "admin123")
    ).strip()
    DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "").strip()

    # Database
    MONGODB_URI: str = os.getenv("MONGODB_URI", "").strip("\"' ")
    DB_NAME: str = os.getenv("DB_NAME", "NAUKRI_BOT").strip("\"' ")

    # Directories
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()

    # Browser Automation
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")

    # CORS & Domains (strictly configured origins, no open wildcards)
    FRONTEND_URL: str = os.getenv(
        "FRONTEND_URL",
        "http://localhost:5173,http://localhost:3000,http://localhost:8000",
    ).strip()
    ALLOWED_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            f"{FRONTEND_URL},http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:8000,http://localhost:8000",
        ).split(",")
        if origin.strip()
    ]

    # Google Sheets
    GOOGLE_SHEET_URL: str = os.getenv(
        "GOOGLE_SHEET_URL",
        "https://docs.google.com/spreadsheets/d/1-J4aod-jEImTQ1QQDM9seK7oVqYpTxn9-Tzj2V-rMNQ/edit?usp=sharing",
    ).strip()
    GOOGLE_SHEET_WEBHOOK_URL: str = os.getenv("GOOGLE_SHEET_WEBHOOK_URL", "").strip()

    # AI Providers
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()

    # Memory guard & watchdog thresholds
    MEMORY_GUARD_THRESHOLD_MB: float = float(
        os.getenv("MEMORY_GUARD_THRESHOLD_MB", "1500.0")
    )
    MEM_SOFT_LIMIT_PCT: float = float(os.getenv("MEM_SOFT_LIMIT_PCT", "70.0"))
    MEM_HARD_LIMIT_PCT: float = float(os.getenv("MEM_HARD_LIMIT_PCT", "85.0"))
    MEM_CRITICAL_LIMIT_PCT: float = float(os.getenv("MEM_CRITICAL_LIMIT_PCT", "92.0"))
    MEM_RESUME_HYSTERESIS_PCT: float = float(
        os.getenv("MEM_RESUME_HYSTERESIS_PCT", "65.0")
    )
    BROWSER_IDLE_RECYCLE_HOURS: int = int(os.getenv("BROWSER_IDLE_RECYCLE_HOURS", "12"))

    # Daily Quota Timezone
    DAILY_LIMIT_TZ: str = os.getenv("DAILY_LIMIT_TZ", "Asia/Kolkata").strip()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k.upper(), v)

    def validate_setup(self) -> List[str]:
        """Validates critical configuration. Fails startup in production if default admin password is used."""
        warnings = []
        if self.ENV == "production":
            if not self.ADMIN_PASSWORD or self.ADMIN_PASSWORD == "admin123":
                raise RuntimeError(
                    "FATAL SECURITY ERROR: In production mode, ADMIN_PASSWORD environment variable must be set to a secure, non-default value."
                )
            if (
                self.SECRET_KEY
                == "prod-secret-key-naukri-apply-bot-v8-secure-entropy-32chars"
            ):
                raise RuntimeError(
                    "FATAL SECURITY ERROR: In production mode, a unique 32+ character SECRET_KEY is mandatory."
                )

        if (
            self.SECRET_KEY
            == "prod-secret-key-naukri-apply-bot-v8-secure-entropy-32chars"
        ):
            warnings.append(
                "SECRET_KEY is using default value. Please set a random 32+ character key in .env."
            )
        if self.ADMIN_PASSWORD == "admin123":
            warnings.append(
                "ADMIN_PASSWORD is set to default 'admin123'. Please update in .env for production."
            )
        return warnings


settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
