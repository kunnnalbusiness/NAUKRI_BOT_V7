"""
Dynamic path resolver for the entire project.
Handles discovery of configuration, data, sessions, resumes, and cache files
so that all scripts work reliably on both local machines and in containerized
deployments (e.g. Render with persistent disk at DATA_DIR).
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Static fallbacks for backward compatibility
DATA_DIR = PROJECT_ROOT / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
RESUMES_DIR = DATA_DIR / "resumes"
CACHE_DIR = DATA_DIR / "cache"
CONFIG_DIR = PROJECT_ROOT / "config"
DOCS_DIR = PROJECT_ROOT / "docs"


def get_base_data_dir() -> Path:
    """Returns dynamic persistent data directory based on current DATA_DIR env."""
    env_dir = os.environ.get("DATA_DIR")
    if env_dir and env_dir.strip():
        p = Path(env_dir.strip()).resolve()
    else:
        p = PROJECT_ROOT / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_sessions_dir() -> Path:
    """Returns dynamic sessions directory inside base data dir."""
    p = get_base_data_dir() / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_cache_dir() -> Path:
    """Returns dynamic cache directory inside base data dir."""
    p = get_base_data_dir() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_runtime_config_dir() -> Path:
    """Returns dynamic config directory for runtime encrypted settings."""
    p = get_base_data_dir() / "config"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_session_path(site: str = "naukri", username: str = None) -> Path:
    """Finds session file in dynamic DATA_DIR/sessions or falls back to project root/local data, with user scoping."""
    clean_site = site.lower().strip()
    if clean_site.endswith(".json"):
        clean_site = clean_site[:-5].replace("session_", "")

    if username and username.strip().lower() not in ("admin", ""):
        u_suffix = f"_{username.strip().lower()}"
    else:
        u_suffix = ""

    filename = f"session_{clean_site}{u_suffix}.json"
    primary = get_sessions_dir() / filename

    if os.environ.get("DATA_DIR"):
        return primary

    if primary.exists():
        return primary
    candidate2 = PROJECT_ROOT / "data" / "sessions" / filename
    if candidate2.exists():
        return candidate2
    candidate3 = PROJECT_ROOT / filename
    if candidate3.exists():
        return candidate3

    # Fallback only for admin or un-suffixed legacy session
    if not u_suffix:
        legacy_name = f"session_{clean_site}.json"
        legacy_path = get_sessions_dir() / legacy_name
        if legacy_path.exists():
            return legacy_path
        if (PROJECT_ROOT / legacy_name).exists():
            return PROJECT_ROOT / legacy_name

    return primary


def get_cache_path(filename: str = ".applied_cache.json", username: str = None) -> Path:
    """Finds cache file in dynamic DATA_DIR/cache or falls back to project root, with user scoping."""
    if username and username.strip().lower() not in ("admin", ""):
        u_clean = username.strip().lower()
        if filename.endswith(".json"):
            filename = f"{filename[:-5]}_{u_clean}.json"
        else:
            filename = f"{filename}_{u_clean}"

    primary = get_cache_dir() / filename
    if os.environ.get("DATA_DIR"):
        return primary

    if primary.exists():
        return primary
    candidate2 = PROJECT_ROOT / "data" / "cache" / filename
    if candidate2.exists():
        return candidate2
    candidate3 = PROJECT_ROOT / filename
    if candidate3.exists():
        return candidate3
    return primary


def get_learned_answers_path() -> Path:
    """Finds learned_answers.json in DATA_DIR/cache or falls back to project root."""
    return get_cache_path("learned_answers.json")


def get_resume_path(filename: str = "") -> Path:
    """Finds resume in dynamic DATA_DIR/resumes, data/resumes, or project root."""
    resumes_dir = get_base_data_dir() / "resumes"
    resumes_dir.mkdir(parents=True, exist_ok=True)

    clean_name = Path(filename).name if filename else ""
    if clean_name:
        candidates = [
            resumes_dir / clean_name,
            PROJECT_ROOT / "data" / "resumes" / clean_name,
            PROJECT_ROOT / "resumes" / clean_name,
            PROJECT_ROOT / clean_name,
        ]
        for c in candidates:
            if c.exists():
                return c
        return resumes_dir / clean_name

    # If no filename provided, pick first available resume
    for r_dir in [resumes_dir, PROJECT_ROOT / "data" / "resumes", PROJECT_ROOT]:
        if r_dir.exists():
            for f in r_dir.glob("*.doc*"):
                return f
            for f in r_dir.glob("*.pdf"):
                return f
    return resumes_dir / "resume.docx"


def get_config_path(filename: str = "profile.yaml") -> Path:
    """Finds profile config file in project config/ or DATA_DIR/config."""
    candidates = [
        PROJECT_ROOT / "config" / filename,
        get_base_data_dir() / "config" / filename,
        PROJECT_ROOT / filename,
    ]
    for c in candidates:
        if c.exists():
            return c
    return PROJECT_ROOT / "config" / filename


def get_runtime_config_path() -> Path:
    """Path to the encrypted runtime config store."""
    return get_runtime_config_dir() / "runtime.json"


def get_env_path() -> Path:
    """Finds .env in project root or DATA_DIR."""
    candidate1 = PROJECT_ROOT / ".env"
    if candidate1.exists():
        return candidate1
    candidate2 = get_base_data_dir() / ".env"
    if candidate2.exists():
        return candidate2
    return candidate1


def has_session_file(site: str = "naukri", username: str = None) -> bool:
    """Returns True if valid session file exists on disk for specified site and user."""
    p = get_session_path(site, username=username)
    return p.exists() and p.stat().st_size > 10
