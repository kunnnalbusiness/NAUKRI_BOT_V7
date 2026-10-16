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

        cards = page.query_selector_all('div[role="button"][componentkey*="job-card"], div[componentkey*="job-card"]')

        for idx in range(min(4, len(cards))):
            card = cards[idx]
            card.scroll_into_view_if_needed()
            card.click()
            time.sleep(2.5)

            btn_details = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, a[role="button"]'));
                for (const b of btns) {
                    const r = b.getBoundingClientRect();
                    const txt = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    const isEasy = (txt === 'easy apply' || aria.includes('easy apply')) && !aria.includes('filter');
                    if (isEasy && r.x > 500 && r.y > 180 && r.width > 25 && !b.disabled) {
                        return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
                    }
                }
                return null;
            }""")

            if btn_details:
                page.mouse.click(btn_details['x'], btn_details['y'])
                time.sleep(2.5)

                # Inspect all elements with "Apply to "
                info = page.evaluate("""() => {
                    const allEls = Array.from(document.querySelectorAll('*'));
                    const match = allEls.find(el => (el.innerText || '').trim().startsWith('Apply to ') && el.children.length === 0);
                    if (!match) return { found: false };

                    let cur = match;
                    const path = [];
                    while (cur && cur.tagName !== 'BODY') {
                        path.push({
                            tag: cur.tagName,
                            id: cur.id,
                            role: cur.getAttribute('role'),
                            cls: cur.className,
                            w: cur.getBoundingClientRect().width,
                            h: cur.getBoundingClientRect().height
                        });
                        cur = cur.parentElement;
                    }
                    return { found: true, path };
                }""")
                import json
                print("Modal container hierarchy:")
                print(json.dumps(info, indent=2))
                break

    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.close()
