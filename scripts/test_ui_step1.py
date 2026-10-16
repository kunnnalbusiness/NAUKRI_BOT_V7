"""
Test UI Step 1:
Opens headed Playwright Chromium, logs into http://localhost:8000 as admin,
navigates to Sessions, clicks Browser Login, tracks state and takes screenshot.
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACTS_DIR = Path(r"C:\Users\Sakshi\.gemini\antigravity-ide\brain\43d1a55c-aa65-4783-8c6d-faaa9824326b\screenshots")
LOCAL_DIR = Path(r"c:\Users\Sakshi\Desktop\Naukri\v8\naukri-job\data\screenshots")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_DIR.mkdir(parents=True, exist_ok=True)

def run():
    console_logs = []
    page_errors = []
    failed_requests = []

    print("[Step 1] Launching Playwright headed browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url} - {req.failure}"))

        print("[Step 1] Navigating to http://localhost:8000/login...")
        page.goto("http://localhost:8000/login", wait_until="networkidle")
        time.sleep(1)

        print("[Step 1] Filling login form...")
        page.locator("input[placeholder*='admin']").fill("admin")
        import os
        page.locator("input[type='password']").fill(os.getenv("ADMIN_PASSWORD", "testAdminPass123!"))
        page.locator("button[type='submit']").click()

        print("[Step 1] Waiting for dashboard navigation...")
        page.wait_for_timeout(2000)
        print(f"[Step 1] Current URL after login: {page.url}")

        print("[Step 1] Navigating to /sessions via sidebar link...")
        sessions_link = page.locator("a[href='/sessions']").first
        sessions_link.wait_for(state="visible", timeout=10000)
        sessions_link.click()
        page.wait_for_timeout(2000)
        print(f"[Step 1] Current URL: {page.url}")

        print("[Step 1] Waiting for 'Browser Login' button...")
        login_btn = page.locator("button:has-text('Browser Login')").first
        login_btn.wait_for(state="visible", timeout=10000)
        
        print("[Step 1] Clicking 'Browser Login' on Naukri card...")
        login_btn.click()

        # Screencast modal opens
        print("[Step 1] Screencast modal opened. Monitoring state transitions for 12 seconds...")
        modal_locator = page.locator("div.fixed.inset-0")
        modal_locator.wait_for(state="visible", timeout=10000)

        state_history = []
        for i in range(24):
            time.sleep(0.5)
            # Find status badge or status text inside modal
            badge_el = page.locator("div.fixed span.font-mono.font-bold.uppercase").first
            status_text_el = page.locator("div.fixed div.truncate, div.fixed span.truncate").first
            
            b_text = badge_el.inner_text() if badge_el.is_visible() else "no-badge"
            s_text = status_text_el.inner_text() if status_text_el.is_visible() else "no-text"
            state_history.append((f"{i*0.5:.1f}s", b_text, s_text))

        print("[Step 1] State transition history:")
        for timestamp, b_text, s_text in state_history:
            print(f"  {timestamp}: [{b_text}] {s_text}")

        # Capture screenshots
        screenshot_local = LOCAL_DIR / "step1_browser_login.png"
        screenshot_artifact = ARTIFACTS_DIR / "step1_browser_login.png"

        page.screenshot(path=str(screenshot_local))
        page.screenshot(path=str(screenshot_artifact))
        print(f"[Step 1] Saved screenshot to {screenshot_local}")
        print(f"[Step 1] Saved screenshot to {screenshot_artifact}")

        final_badge = page.locator("div.fixed span.font-mono.font-bold.uppercase").first.inner_text() if page.locator("div.fixed span.font-mono.font-bold.uppercase").first.is_visible() else "UNKNOWN"
        print(f"[Step 1] FINAL SCREEN STATUS: {final_badge}")

        print(f"\n[Step 1] --- Summary of Console Logs ({len(console_logs)}) ---")
        for log in console_logs[-15:]:
            print(f"   {log}")
            
        print(f"\n[Step 1] --- Summary of Page Errors ({len(page_errors)}) ---")
        for pe in page_errors:
            print(f"   ERROR: {pe}")
            
        print(f"\n[Step 1] --- Summary of Failed Requests ({len(failed_requests)}) ---")
        for fr in failed_requests:
            print(f"   FAILED REQ: {fr}")

        browser.close()

if __name__ == "__main__":
    run()
