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

        for idx in range(min(5, len(cards))):
            card = cards[idx]
            card.scroll_into_view_if_needed()
            card.click()
            time.sleep(2.0)

            # Find Easy Apply button strictly in details pane
            btn_details = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, a[role="button"]'));
                for (const b of btns) {
                    const r = b.getBoundingClientRect();
                    const txt = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    const isEasy = (txt === 'easy apply' || aria.includes('easy apply')) && !aria.includes('filter');
                    if (isEasy && r.x >= 580 && r.y >= 180 && r.y <= 700 && r.width > 25 && !b.disabled) {
                        return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
                    }
                }
                return null;
            }""")

            if btn_details:
                print(f"Card {idx+1}: Found Easy Apply button at ({btn_details['x']}, {btn_details['y']}). Clicking...")
                page.mouse.click(btn_details['x'], btn_details['y'])
                time.sleep(2.0)

                # Test new describe_modal logic
                modal_state = page.evaluate("""() => {
                    let modal = document.querySelector('dialog[open], dialog, [role="dialog"], [data-test-modal], .jobs-easy-apply-modal, .artdeco-modal');
                    if (!modal) {
                        const candidates = Array.from(document.querySelectorAll('dialog, [role="dialog"], div, section'));
                        modal = candidates.find(c => {
                            const r = c.getBoundingClientRect();
                            return r.width > 350 && r.height > 250 && r.width < 1150 && (c.innerText || '').includes('Apply to');
                        });
                    }
                    if (!modal) return { error: 'no dialog found' };

                    const heading = modal.querySelector('h1, h2, h3, header')?.innerText?.trim() || '';
                    const buttons = Array.from(modal.querySelectorAll('button')).map(b => (b.innerText || b.getAttribute('aria-label') || '').trim()).filter(Boolean);
                    const fields = Array.from(modal.querySelectorAll('input, textarea, select')).map(el => ({
                        tag: el.tagName,
                        type: el.type,
                        id: el.id,
                        name: el.name,
                        value: el.value,
                        placeholder: el.placeholder
                    }));

                    return { heading, buttons, fieldsCount: fields.length, fields: fields.slice(0, 6) };
                }""")

                import json
                print("Modal state:", json.dumps(modal_state, indent=2))

                # Dismiss modal safely
                page.evaluate("""() => {
                    const closeBtn = Array.from(document.querySelectorAll('button')).find(b => {
                        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                        return aria.includes('dismiss') || aria.includes('close');
                    });
                    if (closeBtn) closeBtn.click();
                }""")
                time.sleep(1.0)
                page.evaluate("""() => {
                    const discard = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').toLowerCase().includes('discard'));
                    if (discard) discard.click();
                }""")
                print("Modal dismissed successfully.")
                break

    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.close()
