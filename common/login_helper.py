"""
Login helper and session verification module.
Shared between CLI (login_capture.py) and Web Dashboard (session_stream.py).
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from common.paths import get_session_path, PROJECT_ROOT

SITES = {
    "naukri": "https://www.naukri.com/nlogin/login",
    "linkedin": "https://www.linkedin.com/login",
}

CHECK_URLS = {
    "naukri": "https://www.naukri.com/mnjuser/homepage",
    "linkedin": "https://www.linkedin.com/feed/",
}

# Cache verification results: {site: {"status": ..., "last_verified": ...}}
_SESSION_CACHE: Dict[str, Dict[str, Any]] = {}


def is_login_successful(site: str, current_url: str, page=None) -> bool:
    """Detects whether a page has successfully transitioned to an authenticated state."""
    current_url_lower = (current_url or "").lower()

    # Rule 0: Explicit login / challenge / authwall pages are NEVER successful
    unauth_markers = [
        "/login",
        "nlogin",
        "/checkpoint",
        "/uas/login",
        "/authwall",
        "/signup",
        "challenge",
        "checkpoint/challenge",
    ]
    if any(marker in current_url_lower for marker in unauth_markers):
        return False

    if site == "naukri":
        is_dashboard = (
            "/mnjuser/" in current_url_lower
            or "homepage" in current_url_lower
            or "/profile" in current_url_lower
        )
        if is_dashboard:
            return True
        if page:
            try:
                import inspect

                res = page.query_selector(
                    ".nI-gNb-drawer, .view-profile-wrapper, a[href*='mnjuser']"
                )
                if not inspect.iscoroutine(res) and res:
                    return True
            except Exception:
                pass
        return False

    elif site == "linkedin":
        if any(
            sec in current_url_lower for sec in ("/feed", "/mynetwork", "/jobs", "/in/")
        ):
            return True
        if page:
            try:
                import inspect

                res = page.query_selector(
                    "nav.global-nav, .global-nav__me, a[href*='/in/']"
                )
                if not inspect.iscoroutine(res) and res:
                    return True
            except Exception:
                pass
        return False

    return False


def get_session_file(site: str, username: str = None) -> Path:
    """Returns the session file path for the site, optionally scoped to username."""
    return get_session_path(site, username=username)


def has_session_file(site: str, username: str = None) -> bool:
    """Returns True if the session file exists and is non-empty, restoring from MongoDB if needed."""
    p = get_session_file(site, username=username)
    if p.exists() and p.stat().st_size > 5:
        return True
    try:
        from backend.app.db.mongo import get_decrypted_session

        u_clean = (username or "admin").strip().lower()
        restored = get_decrypted_session(u_clean, site)
        if restored:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(restored, encoding="utf-8")
            return p.exists() and p.stat().st_size > 5
    except Exception:
        pass
    return False


def _get_cache_key(site: str, username: str = None) -> str:
    clean_site = site.lower().strip()
    if username and username.strip().lower() not in ("admin", ""):
        return f"{clean_site}_{username.strip().lower()}"
    return clean_site


def save_session_state(context, site: str, username: str = None) -> Path:
    """Saves storage state to user session file and legacy root path if admin."""
    target_path = get_session_path(site, username=username)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(target_path))

    if not username or username.strip().lower() == "admin":
        legacy_out = PROJECT_ROOT / f"session_{site}.json"
        try:
            context.storage_state(path=str(legacy_out))
        except Exception:
            pass

    # Invalidate cache
    cache_key = _get_cache_key(site, username=username)
    _SESSION_CACHE[cache_key] = {
        "present": True,
        "valid": True,
        "status": "Valid",
        "last_verified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": "Session newly saved",
    }
    return target_path


def remove_session(site: str, username: str = None) -> bool:
    """Removes the session file for the site and user."""
    removed = False
    target = get_session_file(site, username=username)
    if target.exists():
        try:
            target.unlink()
            removed = True
        except Exception:
            pass

    cache_key = _get_cache_key(site, username=username)
    _SESSION_CACHE[cache_key] = {
        "present": False,
        "valid": False,
        "status": "Missing",
        "last_verified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": "Session removed",
    }
    return removed


def check_session_status(
    site: str, force_live_check: bool = False, username: str = None
) -> Dict[str, Any]:
    """
    Checks if session is present and optionally performs a headless live check.
    Uses cached result unless force_live_check is True or cache is older than 15 minutes.
    """
    p = get_session_file(site, username=username)
    cache_key = _get_cache_key(site, username=username)
    if not p.exists() or p.stat().st_size < 5:
        # Check MongoDB backup on cold boot
        try:
            from backend.app.db.mongo import get_decrypted_session

            u_clean = (username or "admin").strip().lower()
            restored = get_decrypted_session(u_clean, site)
            if restored:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(restored, encoding="utf-8")
        except Exception:
            pass

    if not p.exists() or p.stat().st_size < 5:
        res = {
            "present": False,
            "valid": False,
            "status": "Missing",
            "last_verified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": "No session file found",
        }
        _SESSION_CACHE[cache_key] = res
        return res

    # 15-minute TTL Cache check
    now_ts = time.time()
    cached = _SESSION_CACHE.get(cache_key)
    if (
        cached
        and not force_live_check
        and cached.get("present")
        and (now_ts - cached.get("_cached_at", 0) < 900)  # 15 min TTL
    ):
        return cached

    # When force_live_check=False: skip the browser entirely and do a fast
    # local cookie inspection.  This prevents blocking in test / CI envs
    # where Playwright binaries may not be available, and is the expected
    # semantic: "don't launch a headless browser just to check".
    if not force_live_check:
        try:
            import json as _json

            data = _json.loads(p.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            c_names = {c.get("name") for c in cookies}

            if site == "naukri":
                has_auth = bool(c_names.intersection({"nauk_at", "nauk_rt", "J", "_t_ds"}))
            elif site == "linkedin":
                has_auth = bool(c_names.intersection({"li_at"}))
            else:
                has_auth = len(cookies) > 0

            status_str = "Valid" if has_auth else "Expired"
            msg = (
                "Active session file present"
                if has_auth
                else "Session file missing authentication token"
            )
            res = {
                "present": True,
                "valid": has_auth,
                "status": status_str,
                "last_verified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": msg,
                "_cached_at": now_ts,
            }
            _SESSION_CACHE[cache_key] = res
            return res
        except Exception:
            res = {
                "present": True,
                "valid": False,
                "status": "Check Failed",
                "last_verified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": "Could not parse session file",
                "_cached_at": now_ts,
            }
            _SESSION_CACHE[cache_key] = res
            return res

    # force_live_check=True: Perform headless check via BrowserManager single Chromium process
    try:
        from backend.app.services.browser_manager import browser_manager

        res = browser_manager.verify_live_session(site=site, username=username or "admin")
        res["_cached_at"] = now_ts
        _SESSION_CACHE[cache_key] = res
        return res
    except Exception as e:
        # Fallback to local cookie token inspection if live browser check encounters error
        try:
            import json

            data = json.loads(p.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            c_names = {c.get("name") for c in cookies}

            if site == "naukri":
                has_auth = bool(
                    c_names.intersection({"nauk_at", "nauk_rt", "J", "_t_ds"})
                )
            elif site == "linkedin":
                has_auth = bool(c_names.intersection({"li_at"}))
            else:
                has_auth = len(cookies) > 0

            status_str = "Valid" if has_auth else "Expired"
            msg = (
                "Active session file present"
                if has_auth
                else "Session file missing authentication token"
            )
            res = {
                "present": True,
                "valid": has_auth,
                "status": status_str,
                "last_verified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": msg,
                "_cached_at": now_ts,
            }
            _SESSION_CACHE[cache_key] = res
            return res
        except Exception:
            res = {
                "present": True,
                "valid": False,
                "status": "Check Failed",
                "last_verified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": f"Verification error: {str(e)[:80]}",
                "_cached_at": now_ts,
            }
            _SESSION_CACHE[cache_key] = res
            return res
