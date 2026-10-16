import re
from pathlib import Path

p = Path("backend/app/services/session_manager.py")
content = p.read_text(encoding="utf-8")

# 1. Update _cleanup
target1 = """            try:
                if sess.page and not sess.page.is_closed():
                    await asyncio.wait_for(sess.page.close(), timeout=2.0)
            except Exception:
                pass
            try:
                if sess.context:
                    await asyncio.wait_for(sess.context.close(), timeout=2.0)
            except Exception:
                pass
            try:
                if sess.browser:
                    await asyncio.wait_for(sess.browser.close(), timeout=2.0)
                except Exception:
                    pass

            logger.info(
                f"[{sess.site}] Chromium browser and context cleanly terminated."
            )"""

replace1 = """            try:
                await browser_manager.async_close_interactive(sess.page, sess.cdp)
            except Exception:
                pass

            logger.info(
                f"[{sess.site}] Interactive screencast page cleanly detached from BrowserManager."
            )"""

assert target1 in content, "target1 not found"
content = content.replace(target1, replace1, 1)

# 2. Update pw start
target2 = """                if self._pw is None:
                    self._pw = await async_playwright().start()
                pw = self._pw
                session.pw = pw"""
replace2 = """                pw = None"""
assert target2 in content, "target2 not found"
content = content.replace(target2, replace2, 1)

# 3. Update connect_over_cdp
target3 = """                                    browser = await pw.chromium.connect_over_cdp(
                                        f"http://127.0.0.1:{bot_port}"
                                    )"""
replace3 = """                                    browser = browser_manager.connect_over_cdp(
                                        f"http://127.0.0.1:{bot_port}"
                                    )"""
assert target3 in content, "target3 not found"
content = content.replace(target3, replace3, 1)

# 4. Update launch block
idx_start = content.find("                # Launch standalone Chromium with realistic desktop parameters and anti-bot evasions")
assert idx_start != -1, "idx_start not found"
idx_end = content.find("                session.cdp = cdp", idx_start)
assert idx_end != -1, "idx_end not found"
idx_end += len("                session.cdp = cdp")

replacement_launch = """                if not is_attached_to_bot:
                    context, page, cdp = browser_manager.create_interactive_login_session(
                        username=username, site=site
                    )
                    session.context = context
                    session.page = page
                    session.cdp = cdp
                else:
                    cdp = await context.new_cdp_session(page)
                    session.cdp = cdp"""

content = content[:idx_start] + replacement_launch + content[idx_end:]

# 5. Update cdp.send in screencastFrameAck and startScreencast
target5 = """                        if cdp:
                            await cdp.send(
                                "Page.screencastFrameAck", {"sessionId": session_id}
                            )"""
replace5 = """                        if cdp:
                            try:
                                await browser_manager.async_send_cdp(
                                    cdp, "Page.screencastFrameAck", {"sessionId": session_id}
                                )
                            except Exception:
                                pass"""
assert target5 in content, "target5 not found"
content = content.replace(target5, replace5, 1)

target6 = """                await cdp.send(
                    "Page.startScreencast",
                    {
                        "format": "jpeg",
                        "quality": 60,
                        "maxWidth": 1024,
                        "maxHeight": 640,
                        "everyNthFrame": 1,
                    },
                )"""
replace6 = """                await browser_manager.async_send_cdp(
                    cdp,
                    "Page.startScreencast",
                    {
                        "format": "jpeg",
                        "quality": 60,
                        "maxWidth": 1024,
                        "maxHeight": 640,
                        "everyNthFrame": 1,
                    },
                )"""
assert target6 in content, "target6 not found"
content = content.replace(target6, replace6, 1)

# 6. Inputs
content = content.replace('await cdp.send(\n                                "Input.dispatchMouseEvent"', 'await browser_manager.async_send_cdp(\n                                cdp,\n                                "Input.dispatchMouseEvent"')
content = content.replace('await cdp.send("Input.insertText"', 'await browser_manager.async_send_cdp(cdp, "Input.insertText"')
content = content.replace('await cdp.send(\n                                "Input.dispatchKeyEvent"', 'await browser_manager.async_send_cdp(\n                                cdp,\n                                "Input.dispatchKeyEvent"')

p.write_text(content, encoding="utf-8")
print("SUCCESS: session_manager.py cleanly updated!")
