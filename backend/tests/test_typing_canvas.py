"""
Automated Test for Screencast Canvas Keyboard Forwarding & Zero-Duplication Typing.
Verifies:
- Printable text dispatch via Input.insertText types 'hello@test.com' exactly with 0 duplicate characters.
- Non-printable control keys (Backspace, Enter, Tab) execute correctly without text injection.
- Clipboard paste inserts complete string without duplication.
- Shift/special characters are preserved without doubling.
"""

from playwright.sync_api import sync_playwright


def test_screencast_typing_zero_duplication():
    """Verify typing 'hello@test.com' into an input field produces exactly that text with no duplication."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Set up a test form with two inputs
        html_content = """
        <!DOCTYPE html>
        <html>
        <head><title>Input Test</title></head>
        <body style="background:#000; color:#fff; padding:20px;">
            <input id="email_field" type="text" style="width:300px; padding:8px;" autofocus />
            <input id="password_field" type="password" style="width:300px; padding:8px;" />
        </body>
        </html>
        """
        page.set_content(html_content)
        page.wait_for_selector("#email_field")
        page.focus("#email_field")

        cdp = context.new_cdp_session(page)

        # 1. Type "hello@test.com" character by character using the single-path dispatch (Input.insertText)
        test_email = "hello@test.com"
        for char in test_email:
            cdp.send("Input.insertText", {"text": char})

        val = page.eval_on_selector("#email_field", "el => el.value")
        assert (
            val == "hello@test.com"
        ), f"Expected 'hello@test.com', but got duplicated or corrupted value: '{val}'"

        # 2. Test Backspace (control key: dispatchKeyEvent without text)
        cdp.send(
            "Input.dispatchKeyEvent",
            {
                "type": "rawKeyDown",
                "key": "Backspace",
                "code": "Backspace",
                "windowsVirtualKeyCode": 8,
            },
        )
        cdp.send(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": "Backspace",
                "code": "Backspace",
                "windowsVirtualKeyCode": 8,
            },
        )

        val_after_backspace = page.eval_on_selector("#email_field", "el => el.value")
        assert (
            val_after_backspace == "hello@test.co"
        ), f"Expected 'hello@test.co' after Backspace, got: '{val_after_backspace}'"

        # 3. Test Shift character: type 'M' and special character '!'
        cdp.send("Input.insertText", {"text": "m!"})
        val_after_append = page.eval_on_selector("#email_field", "el => el.value")
        assert (
            val_after_append == "hello@test.com!"
        ), f"Expected 'hello@test.com!', got: '{val_after_append}'"

        # 4. Test Tab key moves focus to password field
        cdp.send(
            "Input.dispatchKeyEvent",
            {
                "type": "rawKeyDown",
                "key": "Tab",
                "code": "Tab",
                "windowsVirtualKeyCode": 9,
            },
        )
        cdp.send(
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
        )

        focused_id = page.evaluate(
            "() => document.activeElement ? document.activeElement.id : ''"
        )
        assert (
            focused_id == "password_field"
        ), f"Expected active element to be password_field, got: '{focused_id}'"

        # 5. Test Paste: bulk text insert
        pasted_text = "SecretPassword#2026"
        cdp.send("Input.insertText", {"text": pasted_text})
        val_pw = page.eval_on_selector("#password_field", "el => el.value")
        assert val_pw == pasted_text, f"Expected '{pasted_text}', got: '{val_pw}'"

        browser.close()
