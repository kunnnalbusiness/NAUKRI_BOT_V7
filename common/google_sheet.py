"""
Google Sheet synchronization module.
Directly syncs applied jobs to Google Sheets configured dynamically in .env:
GOOGLE_SHEET_URL=https://docs.google.com/spreadsheets/d/.../edit
"""

import os
import re
import json
import csv
import io
import urllib.request
from datetime import datetime
from pathlib import Path
import requests

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from common.paths import get_cache_path
from common.runtime_config import get_config_value

_NOTIFIED_WEBHOOK = False


def get_sheet_url_and_id() -> tuple[str, str]:
    """Dynamically reads Google Sheet URL and parses Sheet ID from runtime config / env."""
    url = get_config_value(
        "GOOGLE_SHEET_URL",
        default="https://docs.google.com/spreadsheets/d/1-J4aod-jEImTQ1QQDM9seK7oVqYpTxn9-Tzj2V-rMNQ/edit?usp=sharing",
    )

    # Extract Sheet ID using regex
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    sheet_id = (
        match.group(1) if match else "1-J4aod-jEImTQ1QQDM9seK7oVqYpTxn9-Tzj2V-rMNQ"
    )
    return url, sheet_id


# Export dynamic GOOGLE_SHEET_URL and SHEET_ID
GOOGLE_SHEET_URL, SHEET_ID = get_sheet_url_and_id()


def get_webhook_url() -> str:
    """Reads GOOGLE_SHEET_WEBHOOK_URL from runtime config / env."""
    return get_config_value("GOOGLE_SHEET_WEBHOOK_URL", default="").strip()


def load_applied_jobs(username: str = None) -> set[tuple[str, str]]:
    """Loads applied jobs from both the live Google Sheet and the local cache, scoped per user."""
    applied_set: set[tuple[str, str]] = set()
    cache_file = get_cache_path(".applied_cache.json", username=username)

    # 1. Load from local user cache
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            for key in data.get("applied_keys", []):
                if isinstance(key, list) and len(key) == 2:
                    applied_set.add((key[0].strip().lower(), key[1].strip().lower()))
        except Exception as e:
            print(f"  (Note: could not read local cache: {e})")

    # 2. Sync from live Google Sheet if accessible
    # Non-admin users only sync if they have explicitly configured their own sheet
    is_non_admin = bool(username and username.strip().lower() not in ("admin", ""))
    url = ""
    sheet_id = ""
    if is_non_admin:
        try:
            from common.db import get_user_settings

            u_settings = get_user_settings(username)
            user_sheet_url = (
                u_settings.get("sheet_config", {}).get("sheet_url", "").strip()
            )
            if user_sheet_url:
                m = re.search(r"/d/([a-zA-Z0-9-_]+)", user_sheet_url)
                if m:
                    url = user_sheet_url
                    sheet_id = m.group(1)
        except Exception:
            pass
    else:
        url, sheet_id = get_sheet_url_and_id()

    if sheet_id:
        sheet_export_url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        )
        try:
            req = urllib.request.Request(
                sheet_export_url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                if content.strip():
                    reader = csv.reader(io.StringIO(content))
                    next(reader, None)
                    for row in reader:
                        # Expected columns: Timestamp, Platform, Title, Company, Status, Reason
                        if len(row) >= 4:
                            title = row[2].strip().lower()
                            company = row[3].strip().lower()
                            status = (
                                row[4].strip().lower() if len(row) >= 5 else "applied"
                            )
                            if status == "applied" and title and company:
                                applied_set.add((title, company))
        except Exception:
            pass  # If offline or sheet empty, local cache is already loaded

    return applied_set


# Alias for backwards compatibility
load_already_applied = load_applied_jobs


_sheet_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="SheetSync")
_cache_lock = threading.RLock()


def _atomic_write_cache(cache_file: Path, data: dict):
    """Safely writes cache data atomically to prevent corrupted or truncated JSON."""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = cache_file.with_name(f"{cache_file.name}.tmp")
    tmp_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(tmp_file, cache_file)


def _post_payload_with_retry(webhook_url: str, payload: dict, retries: int = 2):
    """Executes webhook push in background with automatic retries and 30s timeout."""
    for attempt in range(1, retries + 2):
        try:
            resp = requests.post(webhook_url, json=payload, timeout=30)
            if resp.status_code in (200, 302):
                return True
        except Exception as e:
            if attempt <= retries:
                time.sleep(2)
                continue
            # Non-blocking log
            print(f"  [Google Sheet Sync Warning]: {e} (Attempt {attempt} failed)")
            return False
    return False


def record_application(
    timestamp: str,
    source: str,
    title: str,
    company: str,
    status: str,
    reason: str = "",
    sheet_name: str = "Sheet1",
    role: str = "",
    posted_time: str = "",
    job_url: str = "",
    username: str = None,
):
    """Saves application record locally and streams asynchronously to Google Sheet if user enabled sync."""
    global _NOTIFIED_WEBHOOK

    t_str = str(timestamp).split(".")[0]
    t_clean = (title or "").strip()
    c_clean = (company or "").strip()
    role_clean = (role or "").strip()
    posted_clean = (posted_time or "").strip() or "Today"
    cache_file = get_cache_path(".applied_cache.json", username=username)

    # 1. Update local activity cache for live dashboard feed
    try:
        with _cache_lock:
            data = {"applied_keys": [], "history": []}
            if cache_file.exists():
                try:
                    raw_txt = cache_file.read_text(encoding="utf-8").strip()
                    if raw_txt:
                        data = json.loads(raw_txt)
                except Exception:
                    data = {"applied_keys": [], "history": []}

            if status == "applied" and t_clean and c_clean:
                key = [t_clean.lower(), c_clean.lower()]
                if key not in data.get("applied_keys", []):
                    data.setdefault("applied_keys", []).append(key)

            data.setdefault("history", []).append(
                {
                    "timestamp": t_str,
                    "source": source,
                    "role": role_clean,
                    "title": t_clean,
                    "company": c_clean,
                    "posted_time": posted_clean,
                    "status": status,
                    "reason": reason,
                    "sheet_name": sheet_name,
                    "job_url": job_url,
                }
            )

            _atomic_write_cache(cache_file, data)
    except Exception as e:
        print(f"  (Cache save note: {e})")

    # 2. Check per-user Google Sheets sync configuration (OPTIONAL)
    webhook_url = ""
    if username:
        try:
            from common.db import get_user_settings

            u_settings = get_user_settings(username)
            sheet_cfg = u_settings.get("sheet_config", {})
            user_wh = sheet_cfg.get("webhook_url", "").strip()
            # If user explicitly provided their webhook
            if user_wh:
                webhook_url = user_wh
        except Exception:
            pass

    # If no per-user webhook, check global webhook only if user is admin or unset
    if not webhook_url and (not username or username.strip().lower() == "admin"):
        webhook_url = get_webhook_url()

    # Push to Google Sheet Webhook ONLY IF configured by user
    if webhook_url:
        notes_with_meta = reason
        if role_clean or posted_clean:
            prefix_parts = []
            if role_clean:
                prefix_parts.append(f"Role: {role_clean}")
            if posted_clean:
                prefix_parts.append(f"Posted: {posted_clean}")
            meta_prefix = f"[{' | '.join(prefix_parts)}]"
            notes_with_meta = f"{meta_prefix} {reason}".strip()

        payload = {
            "timestamp": t_str,
            "source": source,
            "role": role_clean or "-",
            "title": t_clean,
            "company": c_clean,
            "posted_time": posted_clean,
            "status": status,
            "reason": notes_with_meta,
            "raw_reason": reason,
            "sheet_name": sheet_name,
            "job_url": job_url or "",
        }
        _sheet_executor.submit(_post_payload_with_retry, webhook_url, payload)
    else:
        # User has not configured Google Sheets sync; bot continues without saving to external sheet
        pass

    return True


def sync_all_history_to_sheet():
    """Pushes all historical applied jobs in cache to Google Sheet."""
    webhook_url = get_webhook_url()
    if not webhook_url:
        print("GOOGLE_SHEET_WEBHOOK_URL is not set in .env. Cannot sync history.")
        return False

    cache_file = get_cache_path(".applied_cache.json")
    if not cache_file.exists():
        print("No cache file found to sync.")
        return False

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        history = data.get("history", [])
        if not history:
            print("History is empty.")
            return False

        print(f"Syncing {len(history)} past applications to Google Sheet...")
        resp = requests.post(webhook_url, json=history, timeout=20)
        if resp.status_code in (200, 302):
            print(f"SUCCESS: {len(history)} records synced to Google Sheet!")
            return True
        else:
            print(f"Sync failed with HTTP status {resp.status_code}")
            return False
    except Exception as e:
        print(f"Sync error: {e}")
        return False


def send_test_row(webhook_url: str = "") -> tuple[bool, str]:
    """Sends a single test row to verify Google Sheet Webhook connectivity."""
    url = webhook_url or get_webhook_url()
    if not url:
        return False, "Google Sheet Webhook URL is not configured."

    payload = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Dashboard Test",
        "role": "Connection Test",
        "title": "Webhook Verification",
        "company": "Render Service",
        "posted_time": "Just now",
        "status": "verified",
        "reason": "Test row triggered from Dashboard",
        "raw_reason": "Test row triggered from Dashboard",
        "sheet_name": "Sheet1",
        "job_url": "https://render.com",
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code in (200, 302):
            return True, f"Successfully delivered test row (HTTP {resp.status_code})"
        return (
            False,
            f"Webhook responded with HTTP status {resp.status_code}: {resp.text[:100]}",
        )
    except requests.exceptions.Timeout:
        return False, "Webhook request timed out (15s)."
    except Exception as e:
        return False, f"Webhook request failed: {str(e)}"


def sync_cache_from_sheet(username: str = None) -> bool:
    """Rebuilds and populates local application activity cache from the live Google Sheet."""
    # Non-admin users should NEVER inherit the default admin sheet!
    is_non_admin = bool(username and username.strip().lower() not in ("admin", ""))
    url = ""
    sid = ""
    if is_non_admin:
        try:
            from common.db import get_user_settings

            u_settings = get_user_settings(username)
            user_sheet_url = (
                u_settings.get("sheet_config", {}).get("sheet_url", "").strip()
            )
            if not user_sheet_url:
                return False
            m = re.search(r"/d/([a-zA-Z0-9-_]+)", user_sheet_url)
            if not m:
                return False
            url = user_sheet_url
            sid = m.group(1)
        except Exception:
            return False
    else:
        url, sid = get_sheet_url_and_id()

    if not sid:
        return False

    try:
        sheet_export_url = (
            f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv"
        )
        req = urllib.request.Request(
            sheet_export_url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        if not content.strip():
            return False

        reader = list(csv.reader(io.StringIO(content)))
        rows = reader[1:] if len(reader) > 1 else []
        if not rows:
            return False

        history = []
        applied_keys = []
        seen_keys = set()

        for r in rows:
            if len(r) < 5:
                continue
            ts = r[0].strip()
            src = r[1].strip()
            title = r[2].strip()
            company = r[3].strip()
            status = r[4].strip().lower()
            reason = r[5].strip() if len(r) > 5 else ""

            role = ""
            posted = ""
            m_role = re.search(r"Role:\s*([^\|\]]+)", reason)
            if m_role:
                role = m_role.group(1).strip()
            m_posted = re.search(r"Posted:\s*([^\|\]]+)", reason)
            if m_posted:
                posted = m_posted.group(1).strip()

            history.append(
                {
                    "timestamp": ts,
                    "source": src,
                    "role": role,
                    "title": title,
                    "company": company,
                    "posted_time": posted,
                    "status": status,
                    "reason": reason,
                    "sheet_name": "Sheet1",
                    "job_url": "",
                }
            )

            if status == "applied" and title and company:
                k = (title.lower(), company.lower())
                if k not in seen_keys:
                    seen_keys.add(k)
                    applied_keys.append([title.lower(), company.lower()])

        cache_file = get_cache_path(".applied_cache.json", username=username)
        cache_data = {"applied_keys": applied_keys, "history": history}
        with _cache_lock:
            _atomic_write_cache(cache_file, cache_data)
        return True
    except Exception as e:
        print(f"  (Sheet sync note: {e})")
        return False


def get_application_activity(limit: int = 25, username: str = None) -> dict:
    """Returns aggregated live application statistics and newest application entries from cache, scoped by user."""
    cache_file = get_cache_path(".applied_cache.json", username=username)
    empty_platform = {
        "applied_today": 0,
        "total_applied": 0,
        "skipped_today": 0,
        "total_skipped": 0,
        "failed_today": 0,
        "total_failed": 0,
    }
    empty_res = {
        "stats": {
            "total_applied": 0,
            "applied_today": 0,
            "applied_radar": 0,
            "applied_sweep": 0,
            "applied_linkedin": 0,
            "total_skipped": 0,
            "naukri": dict(empty_platform),
            "linkedin": dict(empty_platform),
            "naukri_applied_today": 0,
            "naukri_total_applied": 0,
            "naukri_skipped_today": 0,
            "naukri_total_skipped": 0,
            "linkedin_applied_today": 0,
            "linkedin_total_applied": 0,
            "linkedin_skipped_today": 0,
            "linkedin_total_skipped": 0,
        },
        "recent": [],
    }

    is_non_admin = bool(username and username.strip().lower() not in ("admin", ""))

    # If cache file missing or empty
    if not cache_file.exists() or cache_file.stat().st_size == 0:
        if is_non_admin:
            # Check if user has explicit custom sheet
            has_custom_sheet = False
            try:
                from common.db import get_user_settings

                u_settings = get_user_settings(username)
                has_custom_sheet = bool(
                    u_settings.get("sheet_config", {}).get("sheet_url", "").strip()
                )
            except Exception:
                pass
            if has_custom_sheet:
                sync_cache_from_sheet(username=username)
            else:
                # Initialize empty cache for new user
                with _cache_lock:
                    _atomic_write_cache(cache_file, {"applied_keys": [], "history": []})
                return empty_res
        else:
            sync_cache_from_sheet(username=username)

    if not cache_file.exists():
        return empty_res

    try:
        with _cache_lock:
            raw_txt = (
                cache_file.read_text(encoding="utf-8").strip()
                if cache_file.exists()
                else ""
            )
            if not raw_txt:
                if not is_non_admin:
                    sync_cache_from_sheet(username=username)
                    raw_txt = (
                        cache_file.read_text(encoding="utf-8").strip()
                        if cache_file.exists()
                        else ""
                    )
                if not raw_txt:
                    return empty_res

            try:
                data = json.loads(raw_txt)
            except Exception:
                if not is_non_admin:
                    sync_cache_from_sheet(username=username)
                    raw_txt = (
                        cache_file.read_text(encoding="utf-8").strip()
                        if cache_file.exists()
                        else ""
                    )
                data = (
                    json.loads(raw_txt)
                    if raw_txt
                    else {"applied_keys": [], "history": []}
                )

            history = data.get("history", [])

            # If cache exists but has 0 history, attempt one-time auto-sync from sheet ONLY if admin or has custom sheet
            if not history and not is_non_admin:
                sync_cache_from_sheet(username=username)
                try:
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
                    history = data.get("history", [])
                except Exception:
                    pass

        today_prefix = datetime.now().strftime("%Y-%m-%d")

        total_applied = 0
        applied_today = 0
        applied_radar = 0
        applied_sweep = 0
        applied_linkedin = 0
        total_skipped = 0

        naukri_stats = {
            "applied_today": 0,
            "total_applied": 0,
            "skipped_today": 0,
            "total_skipped": 0,
            "failed_today": 0,
            "total_failed": 0,
        }
        linkedin_stats = {
            "applied_today": 0,
            "total_applied": 0,
            "skipped_today": 0,
            "total_skipped": 0,
            "failed_today": 0,
            "total_failed": 0,
        }

        for item in history:
            st = (item.get("status") or "").lower()
            ts = item.get("timestamp") or ""
            sh = item.get("sheet_name") or ""
            src = (item.get("source") or "").lower()
            is_today = ts.startswith(today_prefix)

            if src == "dashboard test":
                continue

            target = linkedin_stats if "linkedin" in src else naukri_stats

            if st == "applied":
                total_applied += 1
                target["total_applied"] += 1
                if is_today:
                    applied_today += 1
                    target["applied_today"] += 1

                if sh == "Sheet2" or "radar" in src:
                    applied_radar += 1
                elif "linkedin" in src:
                    applied_linkedin += 1
                else:
                    applied_sweep += 1
            elif st == "skipped":
                total_skipped += 1
                target["total_skipped"] += 1
                if is_today:
                    target["skipped_today"] += 1
            elif st in ("failed", "error", "stopped"):
                target["total_failed"] += 1
                if is_today:
                    target["failed_today"] += 1

        recent_slice = history[-limit:] if limit > 0 else history
        recent = []
        for it in reversed(recent_slice):
            entry = dict(it)
            entry["platform"] = (
                "linkedin"
                if "linkedin" in (entry.get("source") or "").lower()
                else "naukri"
            )
            recent.append(entry)

        return {
            "stats": {
                "total_applied": total_applied,
                "applied_today": applied_today,
                "applied_radar": applied_radar,
                "applied_sweep": applied_sweep,
                "applied_linkedin": applied_linkedin,
                "total_skipped": total_skipped,
                "naukri": naukri_stats,
                "linkedin": linkedin_stats,
                "naukri_applied_today": naukri_stats["applied_today"],
                "naukri_total_applied": naukri_stats["total_applied"],
                "naukri_skipped_today": naukri_stats["skipped_today"],
                "naukri_total_skipped": naukri_stats["total_skipped"],
                "linkedin_applied_today": linkedin_stats["applied_today"],
                "linkedin_total_applied": linkedin_stats["total_applied"],
                "linkedin_skipped_today": linkedin_stats["skipped_today"],
                "linkedin_total_skipped": linkedin_stats["total_skipped"],
            },
            "recent": recent,
        }
    except Exception:
        return empty_res


def clear_application_activity(username: str = None) -> bool:
    """Clears live activity feed history from cache for the scoped user."""
    cache_file = get_cache_path(".applied_cache.json", username=username)
    try:
        data = {"applied_keys": [], "history": []}
        if cache_file.exists():
            try:
                old = json.loads(cache_file.read_text(encoding="utf-8"))
                data["applied_keys"] = old.get("applied_keys", [])
            except Exception:
                pass
        cache_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except Exception as e:
        print(f"Error clearing application activity: {e}")
        return False
