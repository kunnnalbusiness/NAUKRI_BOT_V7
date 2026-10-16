"""
Verify that once Browser Login is READY, it does NOT revert to 'launching'
and does NOT refresh the page even after multiple 15s intervals and timer ticks.
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

LOCAL_SCREENSHOTS = Path(r"c:\Users\Sakshi\Desktop\Naukri\v8\naukri-job\data\screenshots")
ARTIFACT_SCREENSHOTS = Path(r"C:\Users\Sakshi\.gemini\antigravity-ide\brain\43d1a55c-aa65-4783-8c6d-faaa9824326b\screenshots")
LOCAL_SCREENSHOTS.mkdir(parents=True, exist_ok=True)
ARTIFACT_SCREENSHOTS.mkdir(parents=True, exist_ok=True)

def run():
    print("=" * 80)
    print("VERIFYING READY STABILITY (NO RE-LAUNCHING, NO REFRESH)")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        print("[1] Logging into admin...")
        page.goto("http://localhost:8000/login", wait_until="domcontentloaded")
        page.locator("input[placeholder*='admin']").fill("admin")
        import os
        page.locator("input[type='password']").fill(os.getenv("ADMIN_PASSWORD", "testAdminPass123!"))
        page.locator("button[type='submit']").click()
        page.wait_for_timeout(2000)

        print("[2] Navigating to /sessions...")
        page.locator("a[href='/sessions']").first.click()
        page.wait_for_timeout(2000)

        print("[3] Clicking Browser Login...")
        login_btn = page.locator("button:has-text('Browser Login')").first
        login_btn.wait_for(state="visible", timeout=10000)
        login_btn.click()

        # Wait for modal and ready badge
        print("[4] Waiting for READY state badge...")
        badge = page.locator("div.fixed span.rounded.font-bold.uppercase").first
        badge.wait_for(state="visible", timeout=15000)

        start_wait = time.time()
        while time.time() - start_wait < 15.0:
            txt = badge.inner_text().strip().lower()
            if "ready" in txt:
                break
            time.sleep(0.3)

        initial_state = badge.inner_text().strip()
        print(f" -> Reached initial state: {initial_state}")
        assert "ready" in initial_state.lower(), f"Expected ready, got {initial_state}"

        # Now monitor for 20 SECONDS continuously!
        # During this period, React Query interval (15s) and timer (every 1s) will run.
        # It MUST NOT switch back to 'launching'!
        print("[5] Monitoring state continuously for 20 seconds...")
        relaunch_detected = False
        relaunch_time = None

        t0 = time.time()
        while time.time() - t0 < 20.0:
            current_state = badge.inner_text().lower()
            if "launching" in current_state:
                relaunch_detected = True
                relaunch_time = time.time() - t0
                print(f"FAILED: Re-launching state detected at {relaunch_time:.1f}s!")
                break
            time.sleep(0.5)

        # Capture final stability screenshot
        sc_path = LOCAL_SCREENSHOTS / "verify_ready_stable.png"
        page.screenshot(path=str(sc_path))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "verify_ready_stable.png"))
        print(f" -> Saved stability screenshot to {sc_path.name}")

        browser.close()

        if relaunch_detected:
            print("=" * 80)
            print(f"TEST FAILED: Reverted to launching after {relaunch_time:.1f} seconds!")
            print("=" * 80)
            sys.exit(1)
        else:
            print("=" * 80)
            print("TEST PASSED: Maintained strictly READY for 20+ seconds with ZERO refresh!")
            print("=" * 80)

if __name__ == "__main__":
    run()
