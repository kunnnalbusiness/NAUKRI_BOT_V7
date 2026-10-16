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
        print(f"Cards found: {len(cards)}")

        for idx in range(min(4, len(cards))):
            card = cards[idx]
            card.scroll_into_view_if_needed()
            card.click()
            time.sleep(2.5)

            # Check if this card has an Easy Apply button in the details pane
            btn_details = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, a[role="button"]'));
                for (const b of btns) {
                    const r = b.getBoundingClientRect();
                    const txt = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    const isEasy = (txt === 'easy apply' || aria.includes('easy apply')) && !aria.includes('filter');
                    if (isEasy && r.x > 500 && r.y > 180 && r.width > 25 && !b.disabled) {
                        return {
                            x: Math.round(r.x + r.width / 2),
                            y: Math.round(r.y + r.height / 2),
                            text: b.innerText,
                            aria: b.getAttribute('aria-label'),
                            outerHTML: b.outerHTML.slice(0, 200)
                        };
                    }
                }
                return null;
            }""")

            print(f"Card {idx+1} button details: {btn_details}")
            if btn_details:
                # Use real mouse click on the coordinates!
                print(f"Clicking with page.mouse at ({btn_details['x']}, {btn_details['y']})...")
                page.mouse.click(btn_details['x'], btn_details['y'])
                time.sleep(3)

                # Check what appeared
                dialogs = page.evaluate("""() => {
                    const all = Array.from(document.querySelectorAll('*'));
                    const overlays = all.filter(el => {
                        const r = el.getBoundingClientRect();
                        const z = window.getComputedStyle(el).zIndex;
                        const role = el.getAttribute('role') || '';
                        const tag = el.tagName.toLowerCase();
                        return (role === 'dialog' || role === 'alertdialog' || el.classList.contains('artdeco-modal') || (z && parseInt(z) > 100))
                            && r.width > 200 && r.height > 150;
                    });
                    return overlays.map(o => ({
                        tag: o.tagName,
                        role: o.getAttribute('role'),
                        cls: o.className,
                        w: Math.round(o.getBoundingClientRect().width),
                        h: Math.round(o.getBoundingClientRect().height),
                        text: (o.innerText || '').slice(0, 300)
                    }));
                }""")
                print(f"Overlays/dialogs detected: {len(dialogs)}")
                for d in dialogs:
                    print(f"  Role={d['role']} Tag={d['tag']} Cls={d['cls'][:40]} Text={repr(d['text'][:120])}")

                # Save screenshot to artifact folder
                out_png = PROJECT_ROOT / "scripts" / "diagnostics" / "easy_apply_clicked.png"
                page.screenshot(path=str(out_png))
                print(f"Screenshot saved to {out_png}")
                break

    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.close()
