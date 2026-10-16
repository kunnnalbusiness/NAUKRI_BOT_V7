import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from common.paths import get_session_path
import linkedin_apply

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
        time.sleep(3.5)

        cards = page.query_selector_all('div[role="button"][componentkey*="job-card"], div[componentkey*="job-card"]')
        card = cards[0]
        card.click()
        time.sleep(2.0)

        clicked = linkedin_apply.click_easy_apply_button(page)
        print("Clicked easy apply:", clicked)
        time.sleep(2.0)

        # Click Dismiss button in modal
        print("Clicking dismiss button...")
        page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const closeBtn = btns.find(b => {
                const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                const txt = (b.innerText || '').toLowerCase();
                return (aria.includes('dismiss') || txt.includes('dismiss') || aria.includes('close')) && !aria.includes('job');
            });
            if (closeBtn) closeBtn.click();
        }""")
        time.sleep(1.5)

        # Inspect all buttons and dialogs currently on page
        info = page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            return btns.map(b => ({
                text: (b.innerText || '').trim(),
                aria: b.getAttribute('aria-label') || '',
                cls: b.className,
                x: Math.round(b.getBoundingClientRect().x),
                y: Math.round(b.getBoundingClientRect().y),
                w: Math.round(b.getBoundingClientRect().width),
                h: Math.round(b.getBoundingClientRect().height)
            })).filter(b => b.w > 20 && b.h > 15 && b.x > 300);
        }""")
        import json
        print("Buttons after clicking Dismiss:")
        print(json.dumps(info, indent=2))

    finally:
        browser.close()
