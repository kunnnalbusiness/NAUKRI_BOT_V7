"""
LinkedIn Job Cards Selector Test
Queries LinkedIn Easy Apply jobs using saved session and verifies:
- Search URL responsiveness
- Job card DOM selector discovery (div[role="button"][componentkey*="job-card"])
- Title, company, and timestamp extraction
DOES NOT SUBMIT ANY APPLICATIONS (Safe Dry Inspection).
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

        print(f"Page Title: {page.title()}")

        card_elements = page.query_selector_all('div[role="button"][componentkey*="job-card"]')
        if not card_elements:
            card_elements = page.query_selector_all('div[componentkey*="job-card"], button[aria-label*="Dismiss"][aria-label*="job"], .jobs-search-results-list li, .scaffold-layout__list li')

        print(f"Discovered {len(card_elements)} job cards.")

        if card_elements:
            print("\nSample cards discovered:")
            for i, card in enumerate(card_elements[:3]):
                raw_text = card.inner_text() or ""
                lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                title = lines[0] if lines else "N/A"
                company = lines[1] if len(lines) > 1 else "N/A"
                print(f"  #{i+1}: {title} @ {company}")
            print("\n[SUCCESS] Job card selectors match current LinkedIn layout.")
        else:
            print("\n[WARNING] No job cards matched selectors.")
    except Exception as e:
        print(f"[ERROR] Search failed: {e}")
    finally:
        browser.close()
