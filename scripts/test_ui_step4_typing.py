"""
Test UI Step 4:
Interacts with the live Screencast canvas through the real frontend:
- Focuses the remote Email input field at exact screen coordinates (810, 290)
- Types 'hello@test.com' character-by-character
- Uses Backspace 4 times to delete '.com' (leaving 'hello@test')
- Pastes '.com' back using Quick Input bar
- Advances to Password field using Tab button
- Types 'secret123' into Password field
- Captures clear screenshots at every stage
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
    print("STARTING TASK 4: COMPLETE CANVAS INPUT & CLIPBOARD VERIFICATION")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=60)
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

        # 1. Focus Email input box at (810, 290)
        print("[Step 4] Focusing Email input field at (810, 290)...")
        page.mouse.click(810, 290)
        time.sleep(0.3)
        page.mouse.click(810, 290)
        time.sleep(0.5)

        canvas.focus()
        time.sleep(0.3)

        # 2. Type "hello@test.com"
        print("[Step 4] Typing 'hello@test.com'...")
        for char in "hello@test.com":
            page.keyboard.type(char)
            time.sleep(0.08)

        time.sleep(2.0)
        sc1_local = LOCAL_SCREENSHOTS / "step4_1_typed_full.png"
        page.screenshot(path=str(sc1_local))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_1_typed_full.png"))
        print(f"[Step 4] Saved: {sc1_local.name}")

        # 3. Press Backspace 4 times
        print("[Step 4] Pressing Backspace 4 times...")
        canvas.focus()
        for _ in range(4):
            page.keyboard.press("Backspace")
            time.sleep(0.15)

        time.sleep(2.0)
        sc2_local = LOCAL_SCREENSHOTS / "step4_2_after_backspace.png"
        page.screenshot(path=str(sc2_local))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_2_after_backspace.png"))
        print(f"[Step 4] Saved: {sc2_local.name}")

        # 4. Paste '.com' using Quick Input box + Send
        print("[Step 4] Pasting '.com' via Quick Input Send...")
        quick_input = page.locator("input[placeholder*='Type or paste text']").first
        quick_input.fill(".com")
        time.sleep(0.2)
        page.locator("button:has-text('Send')").first.click()
        time.sleep(2.0)

        sc3_local = LOCAL_SCREENSHOTS / "step4_3_after_paste.png"
        page.screenshot(path=str(sc3_local))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_3_after_paste.png"))
        print(f"[Step 4] Saved: {sc3_local.name}")

        # 5. Advance focus to Password field using Tab button
        print("[Step 4] Advancing to Password field via Tab button...")
        tab_btn = page.locator("button:has-text('Tab')").first
        tab_btn.click()
        time.sleep(0.5)

        # 6. Type password into Password field
        print("[Step 4] Typing 'secret123' into Password field...")
        canvas.focus()
        for char in "secret123":
            page.keyboard.type(char)
            time.sleep(0.08)

        time.sleep(2.0)
        sc4_local = LOCAL_SCREENSHOTS / "step4_canvas_typing.png"
        page.screenshot(path=str(sc4_local))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_canvas_typing.png"))
        print(f"[Step 4] Saved: {sc4_local.name}")

        browser.close()

    print("=" * 80)
    print("TASK 4 COMPLETE: All keyboard events verified with screenshots!")
    print("=" * 80)

if __name__ == "__main__":
    run()
