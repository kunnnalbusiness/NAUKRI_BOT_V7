"""
Diagnostic script to test LinkedIn Easy Apply button detection and modal opening.
Inspects the job details pane for Easy Apply vs External Apply.
DOES NOT SUBMIT (Safe dry run - closes modal immediately if opened).
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
        print(f"Loading LinkedIn search: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)

        cards = page.query_selector_all('div[role="button"][componentkey*="job-card"], div[componentkey*="job-card"], .jobs-search-results-list li, .scaffold-layout__list li')
        print(f"Total cards found: {len(cards)}")

        if not cards:
            print("No cards found.")
            sys.exit(0)

        # Inspect first 3 cards
        for idx in range(min(3, len(cards))):
            card = cards[idx]
            card.scroll_into_view_if_needed()
            card.click()
            time.sleep(3)

            print(f"\n--- Card {idx+1} ---")
            card_lines = [l.strip() for l in (card.inner_text() or "").split("\n") if l.strip()]
            print("Card Title/Company:", card_lines[:2] if card_lines else "Empty")

            # Check details pane buttons
            buttons_info = page.evaluate("""() => {
                // Find details container
                const details = document.querySelector('.jobs-search__job-details, .scaffold-layout__detail, .job-details-jobs-unified-top-card, [data-view-name="job-details"]');
                const root = details || document;
                const btns = Array.from(root.querySelectorAll('button, a[role="button"], a.jobs-apply-button'));
                return btns.map(b => {
                    const r = b.getBoundingClientRect();
                    return {
                        tag: b.tagName,
                        text: (b.innerText || '').trim(),
                        aria: b.getAttribute('aria-label') || '',
                        cls: b.className || '',
                        href: b.getAttribute('href') || '',
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                        disabled: b.disabled || false
                    };
                }).filter(b => b.w > 20 && b.h > 15 && b.y > 100);
            }""")

            print(f"Found {len(buttons_info)} interactive buttons in details area (y > 100):")
            for bi in buttons_info:
                print(f"  [{bi['tag']}] text='{bi['text']}' aria='{bi['aria']}' x={bi['x']} y={bi['y']} w={bi['w']} h={bi['h']} href='{bi['href']}' cls='{bi['cls'][:40]}'")

            # Check specifically for Easy Apply button
            easy_btn = [b for b in buttons_info if "easy apply" in b["text"].lower() or "easy apply" in b["aria"].lower()]
            print(f"Matches for 'Easy Apply': {len(easy_btn)}")
            if easy_btn:
                print(f"  Target Easy Apply button: {easy_btn[0]}")
            else:
                apply_btn = [b for b in buttons_info if "apply" in b["text"].lower() or "apply" in b["aria"].lower()]
                print(f"Other Apply buttons: {apply_btn}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.close()
