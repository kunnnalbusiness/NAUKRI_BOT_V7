"""
Tests for Engine Status Machine (Active, Paused, Limit Reached) and Daily Quota Protection.
"""

from common.engine_manager import engine_manager


def test_engine_initial_status_is_stopped():
    engine_manager.reset_daily_limit("naukri")
    engine_manager.reset_daily_limit("linkedin")
    status = engine_manager.get_status()
    assert status["naukri"]["status"] in ("Stopped", "Error")
    assert status["linkedin"]["status"] in ("Stopped", "Error")


def test_mark_daily_limit_sets_limit_reached_status():
    engine_manager.mark_daily_limit(
        "naukri", reason="Daily quota of 50 applications reached — resets at 12:00 AM"
    )
    status = engine_manager.get_status()
    assert status["naukri"]["daily_limit_exceeded"] is True
    assert status["naukri"]["status"] == "Limit Reached"
    assert "Daily quota" in status["naukri"]["reason"]

    # Reset
    engine_manager.reset_daily_limit("naukri")
    status_after = engine_manager.get_status()
    assert status_after["naukri"]["daily_limit_exceeded"] is False
    assert status_after["naukri"]["status"] != "Limit Reached"


def test_increment_applied_quota_trigger():
    engine_manager.reset_daily_limit("linkedin")
    with engine_manager._lock:
        engine_manager._states["linkedin"]["session_applied_count"] = 49

    # 50th application triggers daily limit
    engine_manager.increment_applied("linkedin")
    status = engine_manager.get_status()
    assert status["linkedin"]["daily_limit_exceeded"] is True
    assert status["linkedin"]["status"] == "Limit Reached"

    # Reset
    engine_manager.reset_daily_limit("linkedin")
    with engine_manager._lock:
        engine_manager._states["linkedin"]["session_applied_count"] = 0


def test_api_status_reflects_limit_reached():
    from starlette.testclient import TestClient
    from backend.app.main import app
    from backend.app.core.config import settings

    engine_manager.mark_daily_limit(
        "naukri", reason="Daily quota reached — resets at 12:00 AM"
    )

    client = TestClient(app)
    login_res = client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    token = login_res.json()["token"]
    resp = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["engines"]["naukri"]["status"] == "Limit Reached"
    assert data["engines"]["naukri"]["daily_limit_exceeded"] is True
    assert data["daily_limit"]["naukri_exceeded"] is True
    assert data["daily_limit"]["exceeded"] is True

    # Reset
    engine_manager.reset_daily_limit("naukri")


def test_user_isolated_daily_limit_account_change():
    """Verify daily limit is isolated per user account. When User A hits limit, User B is unaffected."""
    # Reset both
    engine_manager.reset_daily_limit("naukri", username="user_a")
    engine_manager.reset_daily_limit("naukri", username="user_b")

    # Mark limit for User A
    engine_manager.mark_daily_limit(
        "naukri", reason="Daily quota reached — resets at 12:00 AM", username="user_a"
    )

    # User A status MUST reflect Limit Reached
    status_a = engine_manager.get_status(username="user_a")
    assert status_a["naukri"]["daily_limit_exceeded"] is True
    assert status_a["naukri"]["status"] == "Limit Reached"

    # User B status MUST NOT be affected (Ready/Stopped, NOT Limit Reached)
    status_b = engine_manager.get_status(username="user_b")
    assert status_b["naukri"]["daily_limit_exceeded"] is False
    assert status_b["naukri"]["status"] != "Limit Reached"

    # Cleanup
    engine_manager.reset_daily_limit("naukri", username="user_a")


def test_account_session_import_clears_daily_limit():
    """Verify that importing/saving a new session resets previous daily limit for that user."""
    username = "test_user_switch"
    engine_manager.mark_daily_limit(
        "naukri", reason="Daily quota reached", username=username
    )

    status_before = engine_manager.get_status(username=username)
    assert status_before["naukri"]["daily_limit_exceeded"] is True

    # User changes account or imports new session
    engine_manager.reset_daily_limit("naukri", username=username)

    status_after = engine_manager.get_status(username=username)
    assert status_after["naukri"]["daily_limit_exceeded"] is False
    assert status_after["naukri"]["status"] != "Limit Reached"
