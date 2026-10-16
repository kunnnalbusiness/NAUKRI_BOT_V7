"""
LinkedIn Session & Access Detector Test
Validates saved session cookies, opens headless browser, and checks for:
- 403 Access Denied
- Checkpoints / Login walls
- Cloudflare challenges
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from common.paths import get_session_path
from common.access_detector import check_page_access_denied

session_path = get_session_path("linkedin", username="admin")
print(f"Checking LinkedIn session at: {session_path}")

if not session_path.exists():
    print("[ERROR] Session file does not exist.")
    sys.exit(1)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        storage_state=str(session_path),
        viewport={"width": 1440, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    try:
        print("Navigating to https://www.linkedin.com/feed/ ...")
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        curr_url = page.url
        curr_title = page.title()
        print(f"Current URL   : {curr_url}")
        print(f"Current Title : {curr_title}")

        denied, d_reason = check_page_access_denied(page)
        print(f"Access Denied : {denied} (Reason: {d_reason})")

        is_authwall = any(w in curr_url.lower() for w in ["login", "checkpoint", "authwall", "challenge"])
        print(f"Authwall/Login: {is_authwall}")

        if not denied and not is_authwall:
            print("\n[SUCCESS] LinkedIn session is fully authenticated and active!")
        else:
            print("\n[WARNING] LinkedIn session requires re-authentication.")
    except Exception as e:
        print(f"[ERROR] Navigation exception: {e}")
    finally:
        browser.close()
