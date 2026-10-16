import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from common.paths import get_session_path
from common.time_filter import is_job_within_age_limit, parse_posted_minutes

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
        print(f"Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3.5)

        cards = page.query_selector_all('div[role="button"][componentkey*="job-card"], div[componentkey*="job-card"]')
        print(f"Total cards found: {len(cards)}\n")

        for idx in range(min(5, len(cards))):
            card = cards[idx]
            time_el = card.query_selector("time")
            time_text = (time_el.inner_text() or "").strip() if time_el else ""
            time_dt = time_el.get_attribute("datetime") if time_el else ""

            card_raw = card.inner_text() or ""
            lines = [l.strip() for l in card_raw.split("\n") if l.strip()]

            print(f"--- CARD #{idx+1} ---")
            print(f"  Title / Company: {lines[:2]}")
            print(f"  Has <time> element? {bool(time_el)}")
            print(f"  time_text: {repr(time_text)}")
            print(f"  time_dt  : {repr(time_dt)}")
            print(f"  Full card lines: {lines}")

            # Check what is_job_within_age_limit evaluates to
            res_with_fallback, reason_fallback = is_job_within_age_limit(text=time_text or card_raw, datetime_attr=time_dt)
            print(f"  Current logic result: allowed={res_with_fallback}, reason={reason_fallback}")

            if time_text:
                res_time_only, reason_time_only = is_job_within_age_limit(text=time_text, datetime_attr=time_dt)
                print(f"  Time-only result   : allowed={res_time_only}, reason={reason_time_only}")

            # Also check if card was clicked, what does details pane have?
            card.scroll_into_view_if_needed()
            card.click()
            time.sleep(2.0)

            details_time_info = page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('time, [class*="posted"], [class*="date"]'));
                return els.filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.x > 500 && r.y > 100 && r.y < 800;
                }).map(el => ({
                    tag: el.tagName,
                    text: (el.innerText || '').trim(),
                    datetime: el.getAttribute('datetime') || ''
                }));
            }""")
            print(f"  Details pane time elements: {details_time_info}\n")

    finally:
        browser.close()
