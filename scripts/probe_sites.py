"""
Diagnostic probe to test live access to naukri.com and linkedin.com using Playwright Chromium
with realistic desktop settings (normal user-agent, en-IN, Asia/Kolkata, 1280x800).
"""
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from common.access_detector import check_page_access_denied

def probe_site(site_name: str, url: str):
    print(f"\n==========================================")
    print(f"Probing {site_name}: {url}")
    print(f"==========================================")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            }
        )
        page = context.new_page()

        t0 = time.perf_counter()
        response_status = None
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=20000)
            response_status = resp.status if resp else None
        except Exception as e:
            print(f"Navigation exception: {e}")

        elapsed = time.perf_counter() - t0
        final_url = page.url
        title = page.title()

        is_blocked, block_msg = check_page_access_denied(page, site=site_name, response_status=response_status)

        print(f"HTTP Status: {response_status}")
        print(f"Elapsed: {elapsed:.2f}s")
        print(f"Page Title: '{title}'")
        print(f"Final URL: {final_url}")
        print(f"Access Denied Detected: {is_blocked}")
        if is_blocked:
            print(f"Block Message: {block_msg}")
        else:
            print(f"Access Status: GRANTED / REACHABLE")

        page.close()
        context.close()
        browser.close()

if __name__ == "__main__":
    probe_site("naukri", "https://www.naukri.com/nlogin/login")
    probe_site("linkedin", "https://www.linkedin.com/login")
