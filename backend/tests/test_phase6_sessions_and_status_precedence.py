"""
Phase 6 Tests: Encrypted MongoDB session storage with read-back verification,
strict production failures (no local fake-success fallback), independent daily_limits collection
keyed by (username, site, date) in DAILY_LIMIT_TZ, and centralized status precedence.
"""

import pytest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from backend.app.core.config import settings
from backend.app.db.mongo import (
    save_encrypted_session,
    get_decrypted_session,
    get_daily_applied_count,
    increment_daily_applied_count,
    is_daily_limit_reached,
    compute_engine_status,
)


class TestPhase6SessionsAndPrecedence:
    def test_save_encrypted_session_read_back_verification(self):
        """Saving session must encrypt, save, and verify read-back match before success."""
        username = "test_sess_user"
        site = "naukri"
        dummy_state = (
            '{"cookies":[{"name":"test_nauk","value":"secret_val"}],"origins":[]}'
        )

        # Successful save and read-back
        success = save_encrypted_session(username, site, dummy_state)
        assert success is True

        # Read back decrypted session
        restored = get_decrypted_session(username, site)
        assert restored == dummy_state

    def test_production_mongo_failure_never_returns_fake_success(self):
        """In production mode, if MongoDB is unreachable or write fails, it must raise a genuine error."""
        with patch.object(settings, "ENV", "production"):
            with patch("backend.app.db.mongo.get_db", return_value=None):
                with pytest.raises(RuntimeError) as exc_info:
                    save_encrypted_session("prod_user", "linkedin", '{"cookies":[]}')
                assert "MONGO_UNREACHABLE" in str(exc_info.value)

    def test_daily_limit_counter_independent_of_activity_log(self):
        """Daily quota counter in daily_limits collection is keyed by (username, site, date) and immune to Clear Log."""
        username = "test_quota_user"
        site = "naukri"
        tz = ZoneInfo(settings.DAILY_LIMIT_TZ)
        today_str = datetime.now(tz).strftime("%Y-%m-%d")

        # Initial count
        c0 = get_daily_applied_count(username, site, today_str)
        # Increment count
        c1 = increment_daily_applied_count(username, site, delta=2)
        assert c1 == c0 + 2

        # Verify limit check
        assert is_daily_limit_reached(username, site, limit=c1) is True
        assert is_daily_limit_reached(username, site, limit=c1 + 10) is False

        # Simulate "Clear Log" from activity feed - must NOT reset the daily_limits collection
        from common.google_sheet import clear_application_activity

        clear_application_activity(username=username)

        # Count must remain intact!
        c2 = get_daily_applied_count(username, site, today_str)
        assert (
            c2 == c1
        ), "Clearing live activity log must never reset daily application quota!"

    def test_status_precedence_rules(self):
        """
        compute_engine_status must strictly enforce precedence:
        Session Missing > Profile Incomplete > Busy > Limit Reached > Running > Stopped
        Admin removing session must override Limit Reached.
        """
        username = "test_precedence_user"
        site = "naukri"

        # Case 1: Session Missing overrides Limit Reached
        status1, reason1 = compute_engine_status(
            site=site,
            username=username,
            has_session=False,
            is_profile_complete=True,
            is_busy=False,
            is_limit_reached=True,
            is_running=False,
        )
        assert status1 == "Session Missing"
        assert "Session" in reason1

        # Case 2: Profile Incomplete overrides Limit Reached when session exists
        status2, reason2 = compute_engine_status(
            site=site,
            username=username,
            has_session=True,
            is_profile_complete=False,
            is_busy=False,
            is_limit_reached=True,
            is_running=False,
        )
        assert status2 == "Profile Incomplete"
        assert "profile" in reason2.lower()

        # Case 3: Busy overrides Limit Reached
        status3, reason3 = compute_engine_status(
            site=site,
            username=username,
            has_session=True,
            is_profile_complete=True,
            is_busy=True,
            busy_user="another_user",
            is_limit_reached=True,
            is_running=False,
        )
        assert status3 == "Busy"
        assert "another_user" in reason3

        # Case 4: Limit Reached when all prerequisites met
        status4, reason4 = compute_engine_status(
            site=site,
            username=username,
            has_session=True,
            is_profile_complete=True,
            is_busy=False,
            is_limit_reached=True,
            is_running=False,
        )
        assert status4 == "Limit Reached"

        # Case 5: Running status
        status5, _ = compute_engine_status(
            site=site,
            username=username,
            has_session=True,
            is_profile_complete=True,
            is_busy=False,
            is_limit_reached=False,
            is_running=True,
        )
        assert status5 == "Running"
