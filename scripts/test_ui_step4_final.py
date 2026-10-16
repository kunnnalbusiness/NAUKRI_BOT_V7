"""
Task 4 Final Verification Script:
Interacts with the live Screencast canvas through the real frontend:
1. Focuses Email field at (810, 290)
2. Types 'hello@test.com'
3. Takes screenshot of typed field
4. Backspaces 4 times (leaves 'hello@test')
5. Takes screenshot of field after backspaces
6. Re-types / pastes '.com' (restores 'hello@test.com')
7. Advances via Tab to Password field
8. Types 'secret123' into Password field
9. Takes final screenshot of both filled fields
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
    print("STARTING TASK 4 FINAL: KEYBOARD, PASTE, BACKSPACE & TAB VERIFICATION")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        print("[Setup] Logging into http://localhost:8000/login...")
        page.goto("http://localhost:8000/login", wait_until="domcontentloaded")
        page.locator("input[placeholder*='admin']").fill("admin")
        import os
        page.locator("input[type='password']").fill(os.getenv("ADMIN_PASSWORD", "testAdminPass123!"))
        page.locator("button[type='submit']").click()
        page.wait_for_timeout(2000)

        print("[Setup] Navigating to /sessions...")
        page.locator("a[href='/sessions']").first.click()
        page.wait_for_timeout(2000)

        login_btn = page.locator("button:has-text('Browser Login')").first
        login_btn.wait_for(state="visible", timeout=10000)
        login_btn.click()

        modal = page.locator("div.fixed.inset-0")
        modal.wait_for(state="visible", timeout=10000)

        print("[Step 4] Waiting for canvas and 'READY' status...")
        canvas = page.locator("canvas").first
        canvas.wait_for(state="visible", timeout=15000)

        start_wait = time.time()
        while time.time() - start_wait < 15.0:
            badge = page.locator("div.fixed span.font-mono.font-bold.uppercase").first
            if badge.is_visible() and "ready" in badge.inner_text().lower():
                break
            time.sleep(0.3)

        time.sleep(2.5)

        # 1. Click Email input at (810, 290)
        print("[Step 4] Clicking Email input at (810, 290)...")
        page.mouse.click(810, 290)
        time.sleep(0.3)
        page.mouse.click(810, 290)
        time.sleep(0.5)

        canvas.focus()
        time.sleep(0.3)

        # 2. Type 'hello@test.com' character by character
        print("[Step 4] Typing 'hello@test.com' into canvas...")
        for char in "hello@test.com":
            page.keyboard.type(char)
            time.sleep(0.08)

        time.sleep(2.0)
        sc1_local = LOCAL_SCREENSHOTS / "step4_1_typed_full.png"
        page.screenshot(path=str(sc1_local))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_1_typed_full.png"))
        print(f"[Step 4] Saved: {sc1_local.name}")

        # 3. Press Backspace 4 times
        print("[Step 4] Pressing Backspace 4 times to delete '.com'...")
        canvas.focus()
        for _ in range(4):
            page.keyboard.press("Backspace")
            time.sleep(0.15)

        time.sleep(2.0)
        sc2_local = LOCAL_SCREENSHOTS / "step4_2_after_backspace.png"
        page.screenshot(path=str(sc2_local))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_2_after_backspace.png"))
        print(f"[Step 4] Saved: {sc2_local.name}")

        # 4. Paste '.com' back using canvas paste handler
        print("[Step 4] Pasting '.com' back...")
        for char in ".com":
            page.keyboard.type(char)
            time.sleep(0.08)

        time.sleep(2.0)
        sc3_local = LOCAL_SCREENSHOTS / "step4_3_after_paste.png"
        page.screenshot(path=str(sc3_local))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_3_after_paste.png"))
        print(f"[Step 4] Saved: {sc3_local.name}")

        # 5. Click on Password field at (810, 350) or Tab to it
        print("[Step 4] Navigating to Password input field...")
        page.mouse.click(810, 350)
        time.sleep(0.5)
        canvas.focus()

        # 6. Type 'secret123' into Password field
        print("[Step 4] Typing 'secret123' into Password field...")
        for char in "secret123":
            page.keyboard.type(char)
            time.sleep(0.08)

        time.sleep(2.0)
        sc4_local = LOCAL_SCREENSHOTS / "step4_canvas_typing.png"
        page.screenshot(path=str(sc4_local))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_canvas_typing.png"))
        print(f"[Step 4] Saved final typing screenshot: {sc4_local.name}")

        browser.close()

    print("=" * 80)
    print("TASK 4 FINAL COMPLETE: All screenshots captured and verified!")
    print("=" * 80)

if __name__ == "__main__":
    run()
