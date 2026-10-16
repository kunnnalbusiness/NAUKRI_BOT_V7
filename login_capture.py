"""
Auto-detects and saves login session for Naukri or LinkedIn.

Opens a real, visible Chromium window. You log in by hand — type your
password, complete 2FA, solve any CAPTCHA. As soon as your dashboard /
homepage loads, the script automatically captures your session (cookies +
local storage) and saves it dynamically to data/sessions/session_<site>.json.

Usage:
    python login_capture.py naukri
    python login_capture.py linkedin
"""
import sys
import time
from pathlib import Path
# Using BrowserManager for unified browser lifecycle

from common.paths import get_session_path, SESSIONS_DIR, PROJECT_ROOT
from common.login_helper import SITES, is_login_successful, save_session_state


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SITES:
        print(f"Usage: python login_capture.py [{'|'.join(SITES)}]")
        sys.exit(1)

    site = sys.argv[1]
    url = SITES[site]
    primary_out = SESSIONS_DIR / f"session_{site}.json"

    from backend.app.services.browser_manager import browser_manager

    context = browser_manager.get_or_create_context("admin", site, is_automation=False)
    page = browser_manager.get_sync_page("admin", site)
    page.goto(url)

        print(f"\n=======================================================")
        print(f"Browser window is open at: {url}")
        print("Please log in in the browser window:")
        print("Enter your credentials, OTP, or Google Login.")
        print("Script will AUTOMATICALLY detect when you reach your homepage!")
        print(f"=======================================================\n")

        logged_in = False
        start_time = time.time()

        while True:
            time.sleep(2)
            if page.is_closed():
                print("Browser window was closed.")
                break

            current_url = page.url
            if is_login_successful(site, current_url, page):
                print(f"\n✅ Login detected! Current URL: {current_url}")
                logged_in = True
                break

            # Timeout after 10 minutes
            if time.time() - start_time > 600:
                print("Timed out after 10 minutes.")
                break

        if logged_in:
            time.sleep(2)  # Allow final cookies and tokens to be written
            saved_path = save_session_state(context, site)
            print(f"✅ Session successfully saved to {saved_path}!")
        else:
            print("❌ Login was not completed or timed out. Session not saved.")



if __name__ == "__main__":
    main()
