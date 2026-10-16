import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.paths import get_session_path

session_path = get_session_path("linkedin", username="admin")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        storage_state=str(session_path),
        viewport={"width": 1440, "height": 900}
    )
    page = context.new_page()
    page.goto("https://www.linkedin.com/jobs/search/?keywords=Python%20Developer&f_AL=true&sortBy=DD", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3.5)

    cards = page.query_selector_all('div[role="button"][componentkey*="job-card"], div[componentkey*="job-card"]')
    print(f"Cards found: {len(cards)}")
    if cards:
        card = cards[0]
        # Inspect all text spans and their classes
        spans = card.evaluate("""el => {
            return Array.from(el.querySelectorAll('*')).filter(e => e.children.length === 0 && (e.innerText || '').trim().length > 0).map(e => ({
                tag: e.tagName,
                cls: e.className,
                text: (e.innerText || '').trim(),
                parentCls: e.parentElement ? e.parentElement.className : ''
            }));
        }""")
        import json
        print(json.dumps(spans, indent=2))

    browser.close()
