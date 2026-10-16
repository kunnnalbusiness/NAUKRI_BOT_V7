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
        viewport={"width": 1440, "height": 900}
    )
    page = context.new_page()
    for role in ["Data Engineer", "Python Developer"]:
        url = f"https://www.linkedin.com/jobs/search/?keywords={role.replace(' ', '%20')}&f_AL=true&sortBy=DD"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3.5)
        cards = page.query_selector_all('div[role="button"][componentkey*="job-card"], div[componentkey*="job-card"]')
        print(f"\n================ ROLE: {role} (Total cards: {len(cards)}) ================")
        for idx, card in enumerate(cards[:15]):
            raw = card.inner_text() or ""
            lines = [l.strip() for l in raw.split("\n") if l.strip()]
            title = lines[0] if lines else "Unknown"
            
            # Extract time elements
            time_el = card.query_selector("time")
            time_text = (time_el.inner_text() or "").strip() if time_el else ""
            time_dt = time_el.get_attribute("datetime") if time_el else ""

            # Check spans that have "ago" or "posted"
            posted_text = card.evaluate("""el => {
                const timeEl = el.querySelector('time');
                if (timeEl && (timeEl.innerText || timeEl.getAttribute('datetime'))) {
                    return (timeEl.innerText || '').trim();
                }
                const spans = Array.from(el.querySelectorAll('*')).filter(e => e.children.length === 0);
                for (const s of spans) {
                    const txt = (s.innerText || '').trim();
                    if (/^(?:posted\s+)?(?:\d+\s*(?:m|min|minute|h|hr|hour|d|day|w|wk|week|mo|month|y|year)s?(?:\s*ago)?|just now|today)/i.test(txt) && txt.length < 40 && !txt.toLowerCase().includes('inr') && !txt.toLowerCase().includes('lpa')) {
                        return txt;
                    }
                }
                for (const s of spans) {
                    const txt = (s.innerText || '').trim();
                    if (/ago|just now|today/i.test(txt) && txt.length < 40 && !txt.toLowerCase().includes('inr') && !txt.toLowerCase().includes('lpa')) {
                        return txt;
                    }
                }
                return '';
            }""")

            allowed, reason = is_job_within_age_limit(text=posted_text or time_text, datetime_attr=time_dt)
            mins, mode = parse_posted_minutes(text=posted_text or time_text, datetime_attr=time_dt)

            print(f"[{idx+1}] Title: {title[:35]}")
            print(f"    Extracted Time: '{posted_text}'")
            print(f"    Parsed Mins   : {mins} ({mode})")
            print(f"    Allowed?      : {allowed} ({reason})")
            if allowed:
                print(f"    --> FRESH JOB ACCEPTED: {title}")

    browser.close()
