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
        url = "https://www.linkedin.com/jobs/search/?keywords=Python%20Developer&sortBy=DD"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)

        cards = page.query_selector_all('div[role="button"][componentkey*="job-card"], div[componentkey*="job-card"]')
        print(f"Cards found: {len(cards)}")

        for idx in range(min(5, len(cards))):
            card = cards[idx]
            card.scroll_into_view_if_needed()
            card.click()
            time.sleep(2.0)

            # Analyze details pane
            analysis = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, a[role="button"], a'));
                // Filter to details pane: x >= 550, y between 180 and 800
                const detailsBtns = btns.map(b => {
                    const r = b.getBoundingClientRect();
                    return {
                        tag: b.tagName,
                        text: (b.innerText || '').trim(),
                        aria: (b.getAttribute('aria-label') || '').trim(),
                        href: b.getAttribute('href') || '',
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                        disabled: b.disabled || false
                    };
                }).filter(b => b.x >= 550 && b.y >= 180 && b.y <= 700 && b.w > 20 && b.h > 15);

                const easyBtn = detailsBtns.find(b => {
                    const txt = b.text.toLowerCase();
                    const aria = b.aria.toLowerCase();
                    return (txt === 'easy apply' || aria.includes('easy apply')) && !aria.includes('dismiss');
                });

                const externalApplyBtn = detailsBtns.find(b => {
                    const txt = b.text.toLowerCase();
                    const aria = b.aria.toLowerCase();
                    const isApply = txt === 'apply' || txt.includes('apply on') || aria.includes('apply on') || aria.includes('apply to');
                    const notEasy = !txt.includes('easy apply') && !aria.includes('easy apply');
                    return isApply && notEasy;
                });

                const alreadyApplied = detailsBtns.some(b => {
                    const txt = b.text.toLowerCase();
                    const aria = b.aria.toLowerCase();
                    return txt.includes('applied') || aria.includes('applied');
                });

                return {
                    detailsBtns,
                    hasEasy: !!easyBtn,
                    easyBtn,
                    hasExternal: !!externalApplyBtn,
                    externalBtn: externalApplyBtn,
                    alreadyApplied
                };
            }""")

            print(f"\n--- Job {idx+1} ---")
            print(f"hasEasy: {analysis['hasEasy']}, hasExternal: {analysis['hasExternal']}, alreadyApplied: {analysis['alreadyApplied']}")
            if analysis['easyBtn']:
                print(f"  Easy Apply Button: {analysis['easyBtn']}")
            if analysis['externalBtn']:
                print(f"  External Button: {analysis['externalBtn']}")
            print("  All details buttons:", [(b['tag'], b['text'], b['aria'], b['x'], b['y']) for b in analysis['detailsBtns']])

    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.close()
