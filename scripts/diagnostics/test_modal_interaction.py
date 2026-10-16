"""
Test clicking the real Easy Apply button and inspecting the opened modal.
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from common.paths import get_session_path

session_path = get_session_path("linkedin", username="admin")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        storage_state=str(session_path),
        viewport={"width": 1440, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    try:
        url = "https://www.linkedin.com/jobs/search/?keywords=Python%20Developer&f_AL=true&sortBy=DD"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)

        # Find cards
        cards = page.query_selector_all('div[role="button"][componentkey*="job-card"], div[componentkey*="job-card"]')
        print(f"Cards found: {len(cards)}")

        for idx in range(min(5, len(cards))):
            card = cards[idx]
            card.scroll_into_view_if_needed()
            card.click()
            time.sleep(2.5)

            # Look for Easy Apply button strictly in the details pane (x > 600)
            btn = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const b = btns.find(x => {
                    const r = x.getBoundingClientRect();
                    const txt = (x.innerText || '').trim().toLowerCase();
                    const aria = (x.getAttribute('aria-label') || '').toLowerCase();
                    const isEasy = txt === 'easy apply' || aria.includes('easy apply');
                    return isEasy && r.x > 500 && r.y > 100 && r.width > 30 && !x.disabled;
                });
                if (b) {
                    b.click();
                    return true;
                }
                return false;
            }""")
            print(f"Card {idx+1}: Clicked Easy Apply button in details pane? -> {btn}")
            if btn:
                time.sleep(2.0)
                # Inspect modal
                modal_info = page.evaluate("""() => {
                    const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"], .artdeco-modal, .jobs-easy-apply-modal'));
                    return dialogs.map(d => {
                        const r = d.getBoundingClientRect();
                        return {
                            tag: d.tagName,
                            role: d.getAttribute('role'),
                            cls: d.className,
                            w: Math.round(r.width),
                            h: Math.round(r.height),
                            text: (d.innerText || '').slice(0, 200)
                        };
                    });
                }""")
                print(f"Modal dialogs after click ({len(modal_info)}):")
                for m in modal_info:
                    print(f"  w={m['w']} h={m['h']} text={repr(m['text'][:100])}")

                # Dismiss modal safely
                page.evaluate("""() => {
                    const close = Array.from(document.querySelectorAll('button')).find(b => {
                        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                        return aria.includes('dismiss') || aria.includes('close');
                    });
                    if (close) close.click();
                }""")
                time.sleep(1)
                page.evaluate("""() => {
                    const discard = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').toLowerCase().includes('discard'));
                    if (discard) discard.click();
                }""")
                break
    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.close()
