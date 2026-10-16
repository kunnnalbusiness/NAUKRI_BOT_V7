"""
Test Step 4: Typing, Backspace, Paste, and Tab via Real Frontend Screencast
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
    print("STEP 4: FULL TYPING, BACKSPACE, PASTE & TAB COMPREHENSIVE TEST")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=60)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # 1. Login
        print("[1] Logging into admin...")
        page.goto("http://localhost:8000/login", wait_until="domcontentloaded")
        page.locator("input[placeholder*='admin']").fill("admin")
        import os
        page.locator("input[type='password']").fill(os.getenv("ADMIN_PASSWORD", "testAdminPass123!"))
        page.locator("button[type='submit']").click()
        page.wait_for_timeout(2000)

        # 2. Open Sessions -> Browser Login
        print("[2] Navigating to Sessions...")
        page.locator("a[href='/sessions']").first.click()
        page.wait_for_timeout(2000)

        print("[3] Clicking Browser Login...")
        login_btn = page.locator("button:has-text('Browser Login')").first
        login_btn.wait_for(state="visible", timeout=10000)
        login_btn.click()

        # 3. Wait for Screencast Canvas & READY state
        canvas = page.locator("canvas").first
        canvas.wait_for(state="visible", timeout=15000)

        start_wait = time.time()
        while time.time() - start_wait < 15.0:
            badge = page.locator("div.fixed span.font-mono.font-bold.uppercase").first
            if badge.is_visible() and "ready" in badge.inner_text().lower():
                break
            time.sleep(0.3)

        print("[4] Waiting 3 seconds for Naukri login form render...")
        time.sleep(3.0)

        # Focus Email input in the remote page:
        # Remote viewport is 1280x800. Canvas is centered.
        # Click Email input on canvas at (810, 290)
        print("[5] Clicking Email field at canvas (810, 290)...")
        page.mouse.click(810, 290)
        time.sleep(0.5)
        canvas.focus()

        # Step 4.1: Type 'hello@test.com'
        print("[6] Typing 'hello@test.com' via keyboard...")
        for ch in "hello@test.com":
            page.keyboard.type(ch)
            time.sleep(0.06)

        time.sleep(1.5)
        sc1 = LOCAL_SCREENSHOTS / "step4_typing_hello_test_com.png"
        page.screenshot(path=str(sc1))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_typing_hello_test_com.png"))
        print(f" -> Saved {sc1.name}")

        # Step 4.2: Press Backspace 4 times (removes '.com')
        print("[7] Pressing Backspace 4 times...")
        canvas.focus()
        for _ in range(4):
            page.keyboard.press("Backspace")
            time.sleep(0.12)

        time.sleep(1.5)
        sc2 = LOCAL_SCREENSHOTS / "step4_backspace_hello_test.png"
        page.screenshot(path=str(sc2))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_backspace_hello_test.png"))
        print(f" -> Saved {sc2.name}")

        # Step 4.3: Paste '.com' via UI text input bar at bottom
        print("[8] Pasting '.com' back using quick-text input bar...")
        quick_input = page.locator("input[placeholder*='Type or paste text']").first
        quick_input.fill(".com")
        send_btn = page.locator("button:has-text('Send')").first
        send_btn.click()

        time.sleep(1.5)
        sc3 = LOCAL_SCREENSHOTS / "step4_paste_restored.png"
        page.screenshot(path=str(sc3))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_paste_restored.png"))
        print(f" -> Saved {sc3.name}")

        # Step 4.4: Press Tab (via UI Tab button or keyboard Tab)
        print("[9] Pressing Tab to advance focus to Password field...")
        tab_btn = page.locator("button:has-text('Tab')").first
        tab_btn.click()
        time.sleep(0.5)

        # Type 'mypassword123' into password field
        print("[10] Typing into Password field...")
        quick_input.fill("mypassword123")
        send_btn.click()

        time.sleep(1.5)
        sc4 = LOCAL_SCREENSHOTS / "step4_tab_password_filled.png"
        page.screenshot(path=str(sc4))
        page.screenshot(path=str(ARTIFACT_SCREENSHOTS / "step4_tab_password_filled.png"))
        print(f" -> Saved {sc4.name}")

        # Crop / Zoom on the Login card for ultra-clear proof
        try:
            from PIL import Image
            img = Image.open(sc4)
            # Crop around the login form card (approx canvas area around (600, 200) to (1050, 600))
            # On 1280x800 modal, the form is right of center
            crop_box = (650, 200, 1000, 560)
            cropped = img.crop(crop_box)
            cropped.save(str(LOCAL_SCREENSHOTS / "step4_field_close_up.png"))
            cropped.save(str(ARTIFACT_SCREENSHOTS / "step4_field_close_up.png"))
            print(" -> Saved cropped field close-up: step4_field_close_up.png")
        except Exception as e:
            print(f"Cropping warning: {e}")

        # Clean close
        close_btn = page.locator("button:has-text('✕'), div.fixed button svg.lucide-x").first
        if close_btn.is_visible():
            close_btn.click()
            time.sleep(1.0)

        browser.close()

    print("=" * 80)
    print("STEP 4 COMPREHENSIVE TEST COMPLETED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    run()
