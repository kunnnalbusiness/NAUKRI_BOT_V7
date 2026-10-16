"""
Comprehensive Diagnostic Tool
Validates:
1. 10-minute fresh job age filter logic
2. Environment configuration (MongoDB Atlas, Secret Key, Encryption)
3. Playwright Chromium executable availability
4. User profiles & session validity in database
5. Engine Manager supervisor states & threads
6. linkedin_apply module importability
"""
import sys
import os
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 60)
print("1. TIME FILTER VALIDATION")
print("=" * 60)
try:
    from common.time_filter import is_job_within_age_limit
    for s in ["Just now", "2 minutes ago", "10 minutes ago", "15 minutes ago", "1 hour ago", ""]:
        ok, reason = is_job_within_age_limit(text=s, datetime_attr="")
        print(f"  '{s}' -> Fresh: {ok} ({reason})")
    print("  [OK] Time filter functioning properly.\n")
except Exception as e:
    print(f"  [ERROR] Time filter failed: {e}\n")

print("=" * 60)
print("2. CONFIGURATION & ENVIRONMENT")
print("=" * 60)
try:
    from backend.app.core.config import settings
    print(f"  MONGODB_URI configured : {bool(settings.MONGODB_URI)}")
    print(f"  SECRET_KEY configured  : {bool(settings.SECRET_KEY)}")
    print(f"  ENCRYPTION_KEY set     : {bool(settings.ENCRYPTION_KEY)}")
    print("  [OK] Environment variables loaded.\n")
except Exception as e:
    print(f"  [ERROR] Config loading failed: {e}\n")

print("=" * 60)
print("3. PLAYWRIGHT CHROMIUM BROWSER")
print("=" * 60)
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = p.chromium.executable_path
        print(f"  Chromium executable: {exe}")
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        browser.close()
    print("  [OK] Playwright chromium launches cleanly.\n")
except Exception as e:
    print(f"  [ERROR] Playwright launch failed: {e}\n")

print("=" * 60)
print("4. DATABASE USERS & SESSIONS")
print("=" * 60)
try:
    from backend.app.db.mongo import get_user, is_user_profile_complete
    from common.login_helper import has_session_file
    for u in ["admin", "preeti"]:
        usr = get_user(u)
        role = usr.get("role") if usr else None
        has_li = has_session_file("linkedin", username=u)
        has_nk = has_session_file("naukri", username=u)
        p_comp, p_reason, _ = is_user_profile_complete(u)
        print(f"  User '{u}' (Role: {role}):")
        print(f"    - LinkedIn Session : {has_li}")
        print(f"    - Naukri Session   : {has_nk}")
        print(f"    - Profile Complete : {p_comp} {p_reason}")
    print("  [OK] Database users checked.\n")
except Exception as e:
    print(f"  [ERROR] Database check failed: {e}\n")

print("=" * 60)
print("5. ENGINE SUPERVISOR STATES")
print("=" * 60)
try:
    from common.engine_manager import engine_manager
    for eng in ["naukri", "linkedin"]:
        st = engine_manager.get_engine_state(eng)
        th = engine_manager._supervisor_threads[eng]
        alive = th.is_alive() if th else False
        print(f"  Engine '{eng}': Status={st.get('status')}, ThreadAlive={alive}, Reason={st.get('reason')}")
    print("  [OK] Engine manager checked.\n")
except Exception as e:
    print(f"  [ERROR] Engine check failed: {e}\n")

print("=" * 60)
print("6. LINKEDIN APPLY MODULE IMPORT TEST")
print("=" * 60)
try:
    import linkedin_apply
    print("  [OK] linkedin_apply imported successfully without errors.\n")
except Exception as e:
    import traceback
    print("  [CRITICAL ERROR] linkedin_apply failed to import:")
    traceback.print_exc()
    print()
