"""
Phase 2 Tests: BrowserManager singleton, process-level locking, context reuse,
memory watchdog tiers with hysteresis, automation route blocking, and system metrics.
"""

import os
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings

client = TestClient(app)


def _login_admin():
    res = client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert res.status_code == 200
    token = res.json()["token"]
    csrf = res.json().get("csrf_token", "")
    return {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}


class TestPhase2BrowserManager:
    def test_browser_manager_singleton_and_lockfile(self, tmp_path):
        """BrowserManager must be a singleton and manage process-level lockfile."""
        from backend.app.services.browser_manager import BrowserManager

        bm1 = BrowserManager.get_instance()
        bm2 = BrowserManager.get_instance()
        assert bm1 is bm2, "BrowserManager must be a singleton instance"

        # Lockfile verification
        lock_file = tmp_path / "browser.lock"
        bm1.init_lock(str(lock_file))
        assert lock_file.exists()
        assert lock_file.read_text().strip() == str(os.getpid())

        # Second lock attempt in another process with active PID must fail
        with patch("psutil.pid_exists", return_value=True):
            acquired = bm1.check_lock_status(
                str(lock_file), current_pid=os.getpid() + 999
            )
            assert (
                acquired is False
            ), "Another live PID holding the lock must be rejected"

        # Stale lockfile (PID dead) must be reclaimed
        with patch("psutil.pid_exists", return_value=False):
            acquired = bm1.check_lock_status(
                str(lock_file), current_pid=os.getpid() + 999
            )
            assert acquired is True, "Dead PID lockfile must be reclaimed"

        bm1.release_lock(str(lock_file))
        assert not lock_file.exists()

    def test_browser_lazy_launch_and_context_reuse(self):
        """Browser must be lazily launched, contexts reused across stop/start, and isolated per user+site."""
        from backend.app.services.browser_manager import BrowserManager

        bm = BrowserManager.get_instance()
        # Browser must not be running initially (lazy)
        bm.reset_for_testing()
        assert bm.is_running() is False

        # Mocking browser launch for lightweight unit test
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_context_naukri = MagicMock(name="context_naukri")
        mock_context_linkedin = MagicMock(name="context_linkedin")
        mock_browser.new_context.side_effect = [
            mock_context_naukri,
            mock_context_linkedin,
        ]

        with patch.object(bm, "_launch_browser_internal", return_value=mock_browser):
            # First context request launches browser
            ctx_n1 = bm.get_or_create_context("test_user_a", "naukri")
            assert bm.is_running() is True
            assert ctx_n1 is not None

            # Same user and site must return the exact same context (warm context reuse)
            ctx_n2 = bm.get_or_create_context("test_user_a", "naukri")
            assert ctx_n1 is ctx_n2, "Context must be reused for the same user and site"

            # Stop must NOT close the context; context stays alive (warm)
            bm.mark_engine_stopped("test_user_a", "naukri")
            assert ("test_user_a", "naukri") in bm.get_active_contexts()

            # Second site for same user must be an isolated context on the same browser
            ctx_l1 = bm.get_or_create_context("test_user_a", "linkedin")
            assert ctx_l1 is not ctx_n1, "Different sites must have separate contexts"

            # Context only closes on explicit removal or disconnect
            bm.close_context("test_user_a", "naukri")
            assert ("test_user_a", "naukri") not in bm.get_active_contexts()

    def test_memory_watchdog_tiers_and_hysteresis(self):
        """Memory watchdog evaluates cgroup/psutil metrics with soft, hard, and critical tiers + hysteresis."""
        from backend.app.services.browser_manager import MemoryWatchdog, WatchdogTier

        watchdog = MemoryWatchdog()

        # Normal tier (< 70%)
        with patch.object(watchdog, "get_memory_percent", return_value=55.0):
            tier, action = watchdog.evaluate()
            assert tier == WatchdogTier.NORMAL
            assert action == "NONE"

        # Soft tier (>= 70%, < 85%): Reject new starts, trigger page recycle
        with patch.object(watchdog, "get_memory_percent", return_value=75.0):
            tier, action = watchdog.evaluate()
            assert tier == WatchdogTier.SOFT_LIMIT
            assert action == "RECYCLE_PAGES"

        # Hard tier (>= 85%, < 92%): Pause engines, drop warm contexts
        with patch.object(watchdog, "get_memory_percent", return_value=88.0):
            tier, action = watchdog.evaluate()
            assert tier == WatchdogTier.HARD_LIMIT
            assert action == "PAUSE_ENGINES"

        # Critical tier (>= 92%): Save session & browser relaunch
        with patch.object(watchdog, "get_memory_percent", return_value=95.0):
            tier, action = watchdog.evaluate()
            assert tier == WatchdogTier.CRITICAL
            assert action == "EMERGENCY_RELAUNCH"

        # Hysteresis test:
        # After being in Hard/Critical, dropping to 68% (above 65%) must NOT resume
        with patch.object(watchdog, "get_memory_percent", return_value=68.0):
            tier, action = watchdog.evaluate()
            assert (
                watchdog.can_resume() is False
            ), "Must not resume until memory drops below 65%"

        # Dropping below 65% triggers hysteresis resume
        with patch.object(watchdog, "get_memory_percent", return_value=62.0):
            tier, action = watchdog.evaluate()
            assert (
                watchdog.can_resume() is True
            ), "Must resume when memory drops strictly below 65%"

    def test_metrics_api_endpoint(self):
        """Admin can query /api/system/metrics and receive memory %, RSS, active contexts, and tier."""
        admin_headers = _login_admin()
        res = client.get("/api/system/metrics", headers=admin_headers)
        assert res.status_code == 200
        data = res.json()
        assert "memory_percent" in data
        assert "browser_rss_mb" in data
        assert "active_contexts" in data
        assert "watchdog_tier" in data
        assert "browser_connected" in data
        assert "uptime_seconds" in data
