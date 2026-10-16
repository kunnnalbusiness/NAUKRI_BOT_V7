"""
Validation, Minimum Delay Enforce, and Profile Prerequisite Logic Tests.
"""

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.mongo import create_user, delete_user

client = TestClient(app)


def test_delay_minimum_enforcement():
    """Verify that delay seconds cannot be set below minimum safe limit of 2s."""
    test_user = "delay_test_user"
    test_pass = "pass1234"
    try:
        delete_user(test_user)
    except Exception:
        pass
    create_user(test_user, test_pass, role="user")

    res = client.post(
        "/api/auth/login", json={"username": test_user, "password": test_pass}
    )
    token = res.json()["token"]

    # Attempting delay_seconds = 1 should fail Pydantic ge=2 validation
    bad_res = client.post(
        "/api/user/settings",
        json={"delay_seconds": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad_res.status_code == 422  # Pydantic validation error

    # Safe delay of 3 seconds should succeed
    good_res = client.post(
        "/api/user/settings",
        json={"delay_seconds": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert good_res.status_code == 200

    s = client.get(
        "/api/user/settings", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert s["delay_seconds"] == 3

    delete_user(test_user)


def test_incomplete_profile_blocks_bot_start():
    """Verify that a newly created regular user with incomplete profile cannot start the bot."""
    test_user = "incomplete_profile_user"
    test_pass = "pass1234"
    try:
        delete_user(test_user)
    except Exception:
        pass
    create_user(test_user, test_pass, role="user")

    res = client.post(
        "/api/auth/login", json={"username": test_user, "password": test_pass}
    )
    token = res.json()["token"]

    # Attempt to start engine without completing profile or uploading resume
    start_res = client.post(
        "/api/engine/naukri/start", headers={"Authorization": f"Bearer {token}"}
    )
    assert start_res.status_code == 400
    assert "Pehle profile complete karo" in start_res.json()["detail"]

    delete_user(test_user)
