"""
Browser Matrix Probe (Task 5):
Tests permutations across:
- Headless vs Headed
- Bundled Chromium vs channel="chrome"
- Fresh profile vs Persistent context / Stealth args
For both Naukri and LinkedIn.
Generates screenshots, titles, status codes, and determines the passing configuration to set as default.
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

LOCAL_SCREENSHOTS = Path(r"c:\Users\Sakshi\Desktop\Naukri\v8\naukri-job\data\screenshots")
LOCAL_SCREENSHOTS.mkdir(parents=True, exist_ok=True)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.access_detector import check_page_access_denied

SITES = [
    ("naukri", "https://www.naukri.com/nlogin/login"),
    ("linkedin", "https://www.linkedin.com/login"),
]

CONFIGS = [
    {
        "id": "bundled_headless",
        "name": "Bundled Chromium (Headless)",
        "headless": True,
        "channel": None,
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]
    },
    {
        "id": "bundled_headed",
        "name": "Bundled Chromium (Headed)",
        "headless": False,
        "channel": None,
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]
    },
    {
        "id": "chrome_headless",
        "name": "System Chrome (Headless)",
        "headless": True,
        "channel": "chrome",
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]
    },
    {
        "id": "chrome_headed",
        "name": "System Chrome (Headed)",
        "headless": False,
        "channel": "chrome",
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]
    },
    {
        "id": "chrome_stealth_headed",
        "name": "System Chrome (Headed + Anti-Detect Args)",
        "headless": False,
        "channel": "chrome",
        "args": [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
        ]
    },
]

def run_matrix():
    results = []
    print("=" * 80)
    print("STARTING BROWSER MATRIX TESTING FOR NAUKRI & LINKEDIN")
    print("=" * 80)

    with sync_playwright() as p:
        for site_key, target_url in SITES:
            print(f"\n>>> TESTING SITE: {site_key.upper()} ({target_url})")

            for cfg in CONFIGS:
                cfg_id = f"{site_key}_{cfg['id']}"
                print(f"\n  Running Configuration: {cfg['name']}...")
                screenshot_filename = f"matrix_{cfg_id}.png"
                screenshot_path = LOCAL_SCREENSHOTS / screenshot_filename

                browser = None
                status_code = None
                title = "N/A"
                is_pass = False
                note = ""

                try:
                    launch_kwargs = {
                        "headless": cfg["headless"],
                        "args": cfg["args"],
                    }
                    if cfg["channel"]:
                        launch_kwargs["channel"] = cfg["channel"]

                    browser = p.chromium.launch(**launch_kwargs)
                    context = browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        locale="en-IN",
                        timezone_id="Asia/Kolkata",
                        extra_http_headers={"Accept-Language": "en-US,en;q=0.9,hi;q=0.8"}
                    )
                    page = context.new_page()

                    t0 = time.time()
                    try:
                        resp = page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
                        status_code = resp.status if resp else None
                    except Exception as ge:
                        note = f"Goto error: {str(ge)[:40]}"

                    time.sleep(2)
                    title = page.title()
                    page.screenshot(path=str(screenshot_path))

                    # Assess Pass/Fail
                    is_denied, block_msg = check_page_access_denied(page, site=site_key, response_status=status_code)
                    
                    if is_denied:
                        is_pass = False
                        note = f"Blocked: {block_msg}"
                    elif status_code in (200, 302, 303, 307):
                        # Verify title or presence of form
                        if "access denied" in title.lower() or "blocked" in title.lower():
                            is_pass = False
                            note = f"Access Denied in title: {title}"
                        else:
                            is_pass = True
                            note = "Page rendered successfully"
                    else:
                        is_pass = False
                        note = f"HTTP status {status_code}"

                except Exception as ex:
                    note = f"Exception: {str(ex)[:60]}"
                    is_pass = False
                finally:
                    if browser:
                        try:
                            browser.close()
                        except Exception:
                            pass

                res_record = {
                    "site": site_key,
                    "config_name": cfg["name"],
                    "config_id": cfg["id"],
                    "status_code": status_code,
                    "title": title,
                    "pass": is_pass,
                    "note": note,
                    "screenshot": str(screenshot_path)
                }
                results.append(res_record)
                status_str = "PASS" if is_pass else "FAIL"
                print(f"  Result: [{status_str}] | Status: {status_code} | Title: '{title}' | Note: {note}")
                print(f"  Screenshot: {screenshot_path}")

    print("\n" + "=" * 80)
    print("MATRIX SUMMARY TABLE:")
    print("=" * 80)
    print(f"{'Site':<10} | {'Configuration':<35} | {'HTTP':<5} | {'Status':<6} | {'Page Title'}")
    print("-" * 80)
    for r in results:
        pass_str = "PASS" if r["pass"] else "FAIL"
        print(f"{r['site']:<10} | {r['config_name']:<35} | {str(r['status_code']):<5} | {pass_str:<6} | {r['title'][:30]}")

if __name__ == "__main__":
    run_matrix()
