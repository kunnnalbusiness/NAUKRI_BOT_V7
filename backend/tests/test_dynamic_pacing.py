"""
Test Suite for Dynamic Pacing Controls (Continuous Execution Mode).
Validates:
1. Dynamic pacing clamp (1s - 60s) in EngineManager for Naukri and LinkedIn
2. API endpoint /api/bot/{site}/pacing and /api/engine/{site}/pacing
3. Status endpoint reporting dynamic pace_seconds configuration
4. Input validation and error handling
"""

import pytest
from fastapi.testclient import TestClient
from common.engine_manager import engine_manager
from backend.app.main import app
from backend.app.core.config import settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    res = client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert res.status_code == 200
    data = res.json()
    token = data["token"]
    csrf = data.get("csrf_token", "")
    return {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}


def test_engine_manager_dynamic_pacing():
    """Verify EngineManager sets and clamps pace correctly for both sites."""
    # Naukri pacing
    ok, st = engine_manager.set_pacing("naukri", 4.5)
    assert ok is True
    assert engine_manager.get_pacing("naukri") == 4.5
    assert st["pace_seconds"] == 4.5

    # LinkedIn pacing
    ok, st = engine_manager.set_pacing("linkedin", 2.0)
    assert ok is True
    assert engine_manager.get_pacing("linkedin") == 2.0
    assert st["pace_seconds"] == 2.0

    # Minimum clamp (1.0s)
    ok, st = engine_manager.set_pacing("naukri", 0.2)
    assert ok is True
    assert engine_manager.get_pacing("naukri") == 1.0

    # Maximum clamp (60.0s)
    ok, st = engine_manager.set_pacing("linkedin", 150.0)
    assert ok is True
    assert engine_manager.get_pacing("linkedin") == 60.0

    # Invalid engine site
    ok, err = engine_manager.set_pacing("invalid_portal", 5.0)
    assert ok is False


def test_pacing_api_endpoint(client, auth_headers):
    """Verify /api/bot/{site}/pacing successfully modifies pace and reflects in /api/status."""
    # Set Naukri pace to 3.5s
    res = client.post(
        "/api/bot/naukri/pacing",
        json={"pace_seconds": 3.5},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["site"] == "naukri"
    assert data["pace_seconds"] == 3.5

    # Verify status endpoint reflects new pace
    st_res = client.get("/api/status", headers=auth_headers)
    assert st_res.status_code == 200
    st_data = st_res.json()
    assert st_data["engines"]["naukri"]["pace_seconds"] == 3.5

    # Set LinkedIn pace to 1.0s (Fast mode)
    l_res = client.post(
        "/api/engine/linkedin/pacing",
        json={"pace_seconds": 1.0},
        headers=auth_headers,
    )
    assert l_res.status_code == 200
    assert l_res.json()["pace_seconds"] == 1.0

    # Test missing pace_seconds
    bad_res = client.post(
        "/api/bot/naukri/pacing",
        json={},
        headers=auth_headers,
    )
    assert bad_res.status_code == 400

    # Test invalid site
    inv_res = client.post(
        "/api/bot/unknown/pacing",
        json={"pace_seconds": 2.0},
        headers=auth_headers,
    )
    assert inv_res.status_code == 404
