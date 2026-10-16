"""
Test Suite for Dynamic Fresh Jobs Priority Filter (Backtesting Naukri and LinkedIn).
Validates:
1. Dynamic time filtering with minute/hour thresholds (5m, 10m, 15m, 30m, 60m, 120m)
2. Engine manager dynamic fresh settings and state isolation for both sites
3. API endpoints /api/bot/{site}/fresh-filter and /api/engine/{site}/fresh-filter
4. Status endpoint reporting dynamic fresh configuration
"""

import pytest
from fastapi.testclient import TestClient
from common.time_filter import is_job_within_age_limit
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


def test_dynamic_threshold_minutes_and_hours():
    """Verify that is_job_within_age_limit accurately handles varying dynamic thresholds."""
    # 1. Threshold = 5 minutes
    assert is_job_within_age_limit(text="3 mins ago", max_minutes=5)[0] is True
    assert is_job_within_age_limit(text="6 mins ago", max_minutes=5)[0] is False

    # 2. Threshold = 15 minutes
    assert is_job_within_age_limit(text="12 mins ago", max_minutes=15)[0] is True
    assert is_job_within_age_limit(text="20 mins ago", max_minutes=15)[0] is False

    # 3. Threshold = 30 minutes
    assert is_job_within_age_limit(text="25m ago", max_minutes=30)[0] is True
    assert is_job_within_age_limit(text="45m ago", max_minutes=30)[0] is False

    # 4. Threshold = 1 Hour (60 minutes)
    assert is_job_within_age_limit(text="45 mins ago", max_minutes=60)[0] is True
    assert is_job_within_age_limit(text="1 hour ago", max_minutes=60)[0] is True
    assert is_job_within_age_limit(text="2 hours ago", max_minutes=60)[0] is False

    # 5. Threshold = 2 Hours (120 minutes)
    assert is_job_within_age_limit(text="1 hour ago", max_minutes=120)[0] is True
    assert is_job_within_age_limit(text="2 hours ago", max_minutes=120)[0] is True
    assert is_job_within_age_limit(text="3 hours ago", max_minutes=120)[0] is False


def test_engine_manager_dynamic_fresh_settings():
    """Verify engine_manager updates and retrieves fresh settings independently for each site."""
    # Naukri
    ok, st = engine_manager.set_fresh_filter(
        "naukri", enabled=True, threshold_minutes=15
    )
    assert ok is True
    assert st["only_fresh"] is True
    assert st["fresh_threshold_minutes"] == 15
    en, thresh = engine_manager.get_fresh_settings("naukri")
    assert en is True
    assert thresh == 15

    # LinkedIn
    ok_l, st_l = engine_manager.set_fresh_filter(
        "linkedin", enabled=True, threshold_minutes=120
    )
    assert ok_l is True
    assert st_l["only_fresh"] is True
    assert st_l["fresh_threshold_minutes"] == 120
    en_l, thresh_l = engine_manager.get_fresh_settings("linkedin")
    assert en_l is True
    assert thresh_l == 120

    # Ensure Naukri was not altered by LinkedIn change
    en_n, thresh_n = engine_manager.get_fresh_settings("naukri")
    assert en_n is True
    assert thresh_n == 15

    # Disable Naukri fresh filter
    engine_manager.set_fresh_filter("naukri", enabled=False, threshold_minutes=15)
    en_n2, thresh_n2 = engine_manager.get_fresh_settings("naukri")
    assert en_n2 is False
    assert thresh_n2 == 15


def test_api_fresh_filter_endpoints(client, auth_headers):
    """Verify POST /api/bot/{site}/fresh-filter and /api/engine/{site}/fresh-filter endpoints."""
    # 1. Update Naukri fresh filter via /api/bot/naukri/fresh-filter
    res = client.post(
        "/api/bot/naukri/fresh-filter",
        headers=auth_headers,
        json={"enabled": True, "threshold_minutes": 30},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["site"] == "naukri"
    assert data["enabled"] is True
    assert data["threshold_minutes"] == 30
    assert data["only_fresh"] is True
    assert data["fresh_threshold_minutes"] == 30

    # 2. Update LinkedIn fresh filter via /api/engine/linkedin/fresh-filter (alias)
    res_l = client.post(
        "/api/engine/linkedin/fresh-filter",
        headers=auth_headers,
        json={"enabled": True, "threshold_minutes": 60},
    )
    assert res_l.status_code == 200, res_l.text
    data_l = res_l.json()
    assert data_l["success"] is True
    assert data_l["site"] == "linkedin"
    assert data_l["enabled"] is True
    assert data_l["threshold_minutes"] == 60

    # 3. Verify /api/status returns the updated engine states
    status_res = client.get("/api/status", headers=auth_headers)
    assert status_res.status_code == 200
    engines_data = status_res.json()["engines"]
    assert engines_data["naukri"]["only_fresh"] is True
    assert engines_data["naukri"]["fresh_threshold_minutes"] == 30
    assert engines_data["linkedin"]["only_fresh"] is True
    assert engines_data["linkedin"]["fresh_threshold_minutes"] == 60

    # 4. Toggle off via /api/bot/naukri/fresh-filter with enabled=False
    res_off = client.post(
        "/api/bot/naukri/fresh-filter",
        headers=auth_headers,
        json={"enabled": False, "threshold_minutes": 30},
    )
    assert res_off.status_code == 200
    assert res_off.json()["enabled"] is False
    assert res_off.json()["only_fresh"] is False
