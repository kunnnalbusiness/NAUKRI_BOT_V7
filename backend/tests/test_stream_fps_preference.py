"""
Unit and Integration Tests for Screencast Stream FPS Preference and Throttling.
"""

import pytest
from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.db.mongo import create_user
from backend.app.services.session_manager import ActiveLoginSession


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def auth_token(test_client):
    try:
        create_user("fps_tester", "testpass123", role="user", delay_seconds=4)
    except Exception:
        pass
    res = test_client.post(
        "/api/auth/login", json={"username": "fps_tester", "password": "testpass123"}
    )
    assert res.status_code == 200
    return res.json()["token"]


def test_default_stream_fps(test_client):
    """Verifies that a newly created user has default stream FPS of 15."""
    fresh_user = "fps_brand_new_user"
    try:
        create_user(fresh_user, "testpass123", role="user", delay_seconds=4)
    except Exception:
        pass
    tok = test_client.post(
        "/api/auth/login", json={"username": fresh_user, "password": "testpass123"}
    ).json()["token"]
    res = test_client.get(
        "/api/user/settings", headers={"Authorization": f"Bearer {tok}"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "stream_fps" in data
    assert data["stream_fps"] == 15


def test_update_stream_fps(test_client, auth_token):
    """Verifies updating stream FPS to 30, 60, and 5 via API."""
    for target_fps in [30, 60, 5, 24]:
        res = test_client.post(
            "/api/user/settings",
            json={"stream_fps": target_fps},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert res.status_code == 200
        assert f"{target_fps} FPS" in res.json()["message"]

        # Verify get returns updated value
        check = test_client.get(
            "/api/user/settings", headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert check.status_code == 200
        assert check.json()["stream_fps"] == target_fps


def test_stream_fps_validation(test_client, auth_token):
    """Verifies that invalid FPS (< 1 or > 60) fails Pydantic validation."""
    # ge=1 validation failure
    res_low = test_client.post(
        "/api/user/settings",
        json={"stream_fps": 0},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res_low.status_code == 422

    # le=60 validation failure
    res_high = test_client.post(
        "/api/user/settings",
        json={"stream_fps": 120},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert res_high.status_code == 422


def test_active_session_interval_calculation():
    """Verifies that ActiveLoginSession calculates exact min_frame_interval from FPS."""
    sess = ActiveLoginSession("naukri", mode="live_check")
    assert sess.stream_fps == 15
    assert sess.min_frame_interval == pytest.approx(1.0 / 15.0, rel=1e-4)

    # Test 5 FPS (Eco)
    sess.set_fps(5)
    assert sess.stream_fps == 5
    assert sess.min_frame_interval == pytest.approx(1.0 / 5.0, rel=1e-4)

    # Test 30 FPS (Smooth)
    sess.set_fps(30)
    assert sess.stream_fps == 30
    assert sess.min_frame_interval == pytest.approx(1.0 / 30.0, rel=1e-4)

    # Test 60 FPS (Ultra)
    sess.set_fps(60)
    assert sess.stream_fps == 60
    assert sess.min_frame_interval == pytest.approx(1.0 / 60.0, rel=1e-4)

    # Test clamping
    sess.set_fps(0)
    assert sess.stream_fps == 1
    assert sess.min_frame_interval == pytest.approx(1.0, rel=1e-4)

    sess.set_fps(100)
    assert sess.stream_fps == 60
    assert sess.min_frame_interval == pytest.approx(1.0 / 60.0, rel=1e-4)


def test_user_stream_fps_isolation(test_client):
    """Verifies that two different users maintain independent stream FPS preferences."""
    u1, p1 = "fps_user_alpha", "passAlpha123"
    u2, p2 = "fps_user_beta", "passBeta123"

    try:
        create_user(u1, p1, role="user", delay_seconds=3)
    except Exception:
        pass
    try:
        create_user(u2, p2, role="user", delay_seconds=4)
    except Exception:
        pass

    tok1 = test_client.post(
        "/api/auth/login", json={"username": u1, "password": p1}
    ).json()["token"]
    tok2 = test_client.post(
        "/api/auth/login", json={"username": u2, "password": p2}
    ).json()["token"]

    # User 1 sets 24 FPS
    test_client.post(
        "/api/user/settings",
        json={"stream_fps": 24},
        headers={"Authorization": f"Bearer {tok1}"},
    )
    # User 2 sets 60 FPS
    test_client.post(
        "/api/user/settings",
        json={"stream_fps": 60},
        headers={"Authorization": f"Bearer {tok2}"},
    )

    # Assert isolation
    s1 = test_client.get(
        "/api/user/settings", headers={"Authorization": f"Bearer {tok1}"}
    ).json()
    s2 = test_client.get(
        "/api/user/settings", headers={"Authorization": f"Bearer {tok2}"}
    ).json()

    assert s1["stream_fps"] == 24
    assert s2["stream_fps"] == 60
