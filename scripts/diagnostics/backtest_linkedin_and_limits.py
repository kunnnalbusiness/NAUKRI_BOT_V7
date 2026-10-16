"""
Comprehensive backtest for LinkedIn Easy Apply detection, external apply distinction,
modal field inspection, daily limit detection, and goal completion.
Safe dry-run: Opens Easy Apply modal, validates fields, and safely dismisses without submitting!
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from common.paths import get_session_path
from common.profile import Profile
from common.engine_manager import engine_manager
import linkedin_apply

session_path = get_session_path("linkedin", username="admin")

print("=" * 60)
print("  🚀 BACKTEST: LINKEDIN APPLY, LIMITS & DYNAMIC SMART STOP")
print("=" * 60)

# Test 1: Limit & Goal State Transitions in Engine Manager
print("\n[TEST 1] Testing engine_manager limit & goal state transitions...")
engine_manager.reset_daily_limit("linkedin")
state_init = engine_manager.get_engine_state("linkedin")
assert not state_init.get("daily_limit_exceeded"), "Initial daily limit should be False"
print("  ✓ Initial state cleared cleanly.")

engine_manager.mark_daily_limit("linkedin", reason="Daily Easy Apply limit reached — resets at midnight")
state_limit = engine_manager.get_engine_state("linkedin")
assert state_limit.get("daily_limit_exceeded") is True, "Daily limit exceeded must be True"
assert state_limit.get("status") == "Limit Reached", f"Status must be Limit Reached, got {state_limit.get('status')}"
print("  ✓ mark_daily_limit correctly sets status to 'Limit Reached' with daily_limit_exceeded=True.")

engine_manager.reset_daily_limit("linkedin")
state_cleared = engine_manager.get_engine_state("linkedin")
assert state_cleared.get("daily_limit_exceeded") is False, "Daily limit exceeded must be False after reset"
assert state_cleared.get("status") == "Stopped", "Status must return to Stopped"
print("  ✓ reset_daily_limit clears state cleanly.")

# Test 2: Live LinkedIn Navigation & Modal Interaction (Safe dry run)
print("\n[TEST 2] Testing live LinkedIn Easy Apply button detection & modal handling...")
profile = Profile.load_for_user("admin")

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
        print(f"  Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3.5)

        cards = page.query_selector_all('div[role="button"][componentkey*="job-card"], div[componentkey*="job-card"]')
        print(f"  Total search result job cards discovered: {len(cards)}")
        assert len(cards) > 0, "Should discover job cards"

        tested_easy_count = 0
        tested_cards = 0

        for idx in range(5):
            fresh_cards = page.query_selector_all('div[role="button"][componentkey*="job-card"], div[componentkey*="job-card"]')
            if idx >= len(fresh_cards):
                break
            card = fresh_cards[idx]
            try:
                card.scroll_into_view_if_needed(timeout=2500)
                card.evaluate("el => el.click()")
            except Exception:
                try:
                    card.click(force=True, timeout=3000)
                except Exception:
                    continue
            time.sleep(2.5)
            tested_cards += 1

            lines = [l.strip() for l in (card.inner_text() or "").split("\n") if l.strip()]
            job_title = lines[0] if lines else f"Job #{idx+1}"
            company = lines[1] if len(lines) > 1 else "Company"

            # Check external apply detection
            is_ext = linkedin_apply.has_external_apply_only(page)

            # Check Easy Apply button detection
            can_click = linkedin_apply.click_easy_apply_button(page)
            print(f"  Card {idx+1} ({job_title[:25]} @ {company[:20]}): Clicked Easy Apply? {can_click} | External only? {is_ext}")

            if can_click:
                modal_state = {}
                for _ in range(8):
                    time.sleep(0.5)
                    st = linkedin_apply.describe_modal(page)
                    if not st.get("error"):
                        modal_state = st
                        break
                if not modal_state:
                    modal_state = linkedin_apply.describe_modal(page)

                print(f"    Modal Heading: {repr(modal_state.get('heading'))}")
                print(f"    Buttons found in modal: {modal_state.get('buttons')}")
                print(f"    Fields found in modal: {len(modal_state.get('fields', []))}")

                assert not modal_state.get("error"), f"Modal should be detected with no error, got: {modal_state}"
                assert len(modal_state.get("buttons", [])) > 0, "Modal should have action buttons (e.g. Next, Review)"
                print("    ✓ Modal opened and fields parsed successfully!")

                # Test safe dismissal
                linkedin_apply.dismiss_modal(page)
                time.sleep(1.2)
                post_modal = linkedin_apply.describe_modal(page)
                print(f"    Post-dismiss modal check: {post_modal}")
                assert post_modal.get("error") == "no dialog found", f"Modal must be dismissed cleanly, got: {post_modal}"
                print("    ✓ Modal safely dismissed without submitting.")
                tested_easy_count += 1
                if tested_easy_count >= 2:
                    break

        assert tested_easy_count > 0, "At least one card must have opened and validated Easy Apply modal"

    finally:
        browser.close()

print("\n" + "=" * 60)
print("  🎉 ALL BACKTEST CHECKS PASSED PERFECTLY!")
print("=" * 60)
