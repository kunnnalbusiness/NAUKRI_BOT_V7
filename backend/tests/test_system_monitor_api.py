"""
API Tests: health endpoints, admin-only system monitor, and public status page.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings

client = TestClient(app)


def _login(username=None, password=None):
    res = client.post(
        "/api/auth/login",
        json={
            "username": username or settings.ADMIN_USERNAME,
            "password": password or settings.ADMIN_PASSWORD,
        },
    )
    assert res.status_code == 200
    return res.json()


@pytest.fixture(scope="module")
def admin_token():
    return _login()["token"]


class TestHealthEndpoints:
    def test_healthz_no_auth_required(self):
        res = client.get("/healthz")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_healthz_is_cheap_no_db_call(self):
        # Must not contain DB specifics beyond the env-derived flag
        body = client.get("/healthz").json()
        assert "database" in body

    def test_readyz_no_auth_required(self):
        res = client.get("/readyz")
        assert res.status_code in (200, 503)
        assert "status" in res.json()

    def test_request_id_header_returned(self):
        res = client.get("/healthz", headers={"X-Request-ID": "test-rid-123"})
        assert res.headers.get("X-Request-ID") == "test-rid-123"

    def test_request_id_generated_when_missing(self):
        res = client.get("/healthz")
        rid = res.headers.get("X-Request-ID")
        assert rid and len(rid) == 16


class TestAdminSystemMonitorRBAC:
    def test_stats_requires_auth(self):
        res = client.get("/api/admin/system/stats")
        assert res.status_code == 401

    def test_stats_admin_allowed(self, admin_token):
        res = client.get(
            "/api/admin/system/stats",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert (
            "cpu" in body
            and "memory" in body
            and "workers" in body
            and "mongodb" in body
        )
        assert body["memory"]["process_rss_mb"] > 0

    def test_stats_regular_user_forbidden(self):
        """A standard user must get 403 on admin system endpoints."""
        import time

        uname = f"rbactest{int(time.time())}"
        admin = _login()
        create_res = client.post(
            "/api/admin/users",
            json={"username": uname, "password": "testpass123", "role": "user"},
            headers={"Authorization": f"Bearer {admin['token']}"},
        )
        assert create_res.status_code == 200, create_res.text
        user = _login(uname, "testpass123")
        assert user["role"] == "user"

        res = client.get(
            "/api/admin/system/stats",
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert res.status_code == 403

        # AI key management is now admin-only as well
        res_keys = client.get(
            "/api/keys", headers={"Authorization": f"Bearer {user['token']}"}
        )
        assert res_keys.status_code == 403
        res_add = client.post(
            "/api/keys",
            json={"provider": "gemini", "key": "fake-key-1234567890abcdef"},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert res_add.status_code == 403

    def test_history_admin_only(self, admin_token):
        res = client.get(
            "/api/admin/system/history",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert "history" in res.json()

    def test_incident_note_requires_auth(self):
        # Fresh client with no cookies: must be rejected as unauthenticated
        clean = TestClient(app)
        res = clean.post(
            "/api/admin/system/incidents", json={"component": "api", "note": "x"}
        )
        assert res.status_code == 401

        # Cookie-authenticated without CSRF header must be rejected with 403
        res = client.post(
            "/api/admin/system/incidents", json={"component": "api", "note": "x"}
        )
        assert res.status_code == 403

    def test_incident_note_admin_allowed(self, admin_token):
        res = client.post(
            "/api/admin/system/incidents",
            json={"component": "api", "note": "Deployed new build"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert res.json()["success"] is True


class TestPublicStatusPage:
    def test_summary_public_no_auth(self):
        res = client.get("/api/status/summary")
        assert res.status_code == 200
        body = res.json()
        assert body["overall"] in ("operational", "partial_outage", "major_outage")
        assert len(body["components"]) == 4
        keys = {c["key"] for c in body["components"]}
        assert keys == {"api", "mongodb", "bot_worker", "browser_engine"}

    def test_summary_leaks_nothing_sensitive(self):
        import json as _json

        body = client.get("/api/status/summary").json()
        raw = _json.dumps(body).lower()
        assert "mongodb://" not in raw
        assert "password" not in raw
        assert "secret" not in raw
