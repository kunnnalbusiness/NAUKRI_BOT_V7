"""
Naukri Live Radar — Ultra-Fast Instant Job Scanner & Auto-Applier.

Monitors Naukri 24/7 for newly posted jobs (sorted by freshness: sortBy=f & jobAge=1).
The instant an HR/recruiter publishes a matching job, this bot detects it within seconds,
evaluates role requirements with high precision, auto-answers screening questions with AI,
and applies immediately.

Logs instant applications directly to 'Sheet2' of your Google Sheet.

Usage:
    python live_radar.py
"""
import sys
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import TimeoutError as PWTimeout

from common.profile import Profile
from common import llm
from common import learned_answers
from common import google_sheet
from common.paths import get_session_path
from naukri_apply import (
    passes_filters,
    enumerate_cards,
    check_apply_button,
    click_native_apply,
    answer_screening_chat,
    verify_applied,
    page_has_stop_signal,
    load_already_applied,
    StopRun,
    SkipJob,
)

RADAR_SCAN_INTERVAL_SECONDS = 30  # Wait time between full radar sweeps


def run_live_radar():
    profile = Profile.load()
    session_file = get_session_path("naukri")
    if not session_file.exists():
        raise SystemExit(f"{session_file} not found. Run: python login_capture.py naukri")

    human_timeout = profile.data.get("human_input_timeout_seconds", 120)
    applied_count = 0
    already_applied = load_already_applied()

    print("=" * 65)
    print("      ⚡ NAUKRI LIVE RADAR — INSTANT SCANNER & AUTO-APPLIER ⚡")
    print("=" * 65)
    print(f"Target Roles: {', '.join(profile.target_roles)}")
    print(f"Experience Filter: {profile.total_experience_years} years")
    print(f"Mode: Real-Time Freshness (sortBy=f, jobAge=1)")
    print(f"Target Sheet Tab: Sheet2 ('Instant Live Radar')")
    print(f"Loaded {len(already_applied)} previously applied jobs.")
    print("Watching for new HR postings... (Press Ctrl+C to stop)")
    print("=" * 65)

    from backend.app.services.browser_manager import browser_manager

    page = browser_manager.get_sync_page("admin", "naukri")

        sweep_count = 0
        while True:
            sweep_count += 1
            now_str = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{now_str}] 🛰️  Radar Sweep #{sweep_count} scanning fresh HR postings...")

            for role in profile.target_roles:
                slug = role.lower().replace(" ", "-")
                exp_param = int(profile.total_experience_years)

                # Query newest jobs posted today, sorted strictly by freshness
                url = (
                    f"https://www.naukri.com/{slug}-jobs"
                    f"?experience={exp_param}"
                    f"&jobAge=1"
                    f"&sortBy=f"
                )

                try:
                    page.goto(url, timeout=15000)
                    page.wait_for_selector('.srp-jobtuple-wrapper[data-job-id]', timeout=6000)
                except PWTimeout:
                    continue
                except Exception as e:
                    print(f"  (Radar scan navigation note for {role}: {e})")
                    continue

                stop = page_has_stop_signal(page)
                if stop:
                    print(f"STOPPING RADAR: {stop}")
                    google_sheet.record_application(
                        datetime.now(), "naukri-radar", "-", "-", "stopped", stop, sheet_name="Sheet2"
                    )
                    browser.close()
                    return

                cards = enumerate_cards(page)
                for card in cards:
                    card_title = (card.get("title") or "").strip()
                    card_comp = (card.get("company") or "").strip()

                    if (card_title.lower(), card_comp.lower()) in already_applied:
                        continue

                    # Super accurate filtering: Must match role required keywords and experience
                    ok, reason = passes_filters(card, profile, role)
                    if not ok:
                        continue

                    # Fresh matching job detected!
                    print(f"\n⚡ [NEW POSTING DETECTED] {card_title} @ {card_comp}")
                    print(f"   Applying immediately to be in the first 5 applicants...")

                    try:
                        page.goto(card["href"], timeout=15000)
                        time.sleep(1.5)

                        stop = page_has_stop_signal(page)
                        if stop:
                            raise StopRun(f"stop signal: {stop}")

                        apply_state = check_apply_button(page)
                        if apply_state != "native":
                            already_applied.add((card_title.lower(), card_comp.lower()))
                            continue

                        clicked = click_native_apply(page)
                        if not clicked:
                            continue
                        time.sleep(1.5)

                        answer_screening_chat(
                            page, profile, f"{card_title} at {card_comp}", human_timeout
                        )
                        time.sleep(1.5)

                        # Submission succeeded!
                        applied_count += 1
                        already_applied.add((card_title.lower(), card_comp.lower()))

                        google_sheet.record_application(
                            timestamp=datetime.now(),
                            source="naukri-live-radar",
                            title=card_title,
                            company=card_comp,
                            status="applied",
                            reason="⚡ INSTANT RADAR APPLY (HR Posted)",
                            sheet_name="Sheet2"
                        )

                        print(f"✅ [INSTANT APPLY SUCCESS] Applied to: {card_title} @ {card_comp}")
                        print(f"   Logged directly to Sheet2! Total radar applied: {applied_count}")

                    except SkipJob as e:
                        print(f"  (Skipped: {card_title} — {e})")
                        already_applied.add((card_title.lower(), card_comp.lower()))
                        continue

                    except StopRun as e:
                        print(f"STOPPING: {e}")
                        browser.close()
                        return

                    except Exception as e:
                        print(f"  (Error on {card_title}: {e})")
                        continue

                    time.sleep(3)

            # Sleep between radar sweeps
            time.sleep(RADAR_SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        run_live_radar()
    except KeyboardInterrupt:
        print("\n[INFO] Live Radar stopped by user. Exiting cleanly.")
