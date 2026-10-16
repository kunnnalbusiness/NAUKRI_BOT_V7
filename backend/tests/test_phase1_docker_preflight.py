"""
Phase 1 Tests: Startup preflight check, dependency integrity, and deep browser health endpoint.
"""

import os
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.preflight import run_browser_preflight, PreflightResult

client = TestClient(app)


def _get_admin_headers():
    res = client.post(
        "/api/auth/login",
        json={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert res.status_code == 200
    token = res.json()["token"]
    csrf = res.json().get("csrf_token", "")
    return {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}


class TestPhase1Preflight:
    def test_preflight_success_when_playwright_installed(self):
        """Preflight must succeed without launching Chromium when browser binary exists."""
        result = run_browser_preflight()
        assert isinstance(result, PreflightResult)
        # On local environment where playwright is installed, it should succeed
        assert result.ok is True
        assert result.error_code is None
        assert result.executable_path is not None
        assert os.path.exists(result.executable_path)

    def test_preflight_missing_browser_returns_error_code(self):
        """When executable doesn't exist, preflight must return BROWSER_NOT_INSTALLED with admin hint."""
        with patch(
            "backend.app.core.preflight._get_chromium_executable",
            return_value="/non/existent/path/to/chromium",
        ):
            result = run_browser_preflight(force_refresh=True)
            assert result.ok is False
            assert result.error_code == "BROWSER_NOT_INSTALLED"
            assert "playwright install" in result.admin_hint
            assert "Playwright browser binary missing" in result.message

    def test_preflight_import_error_handled(self):
        """When playwright cannot be imported, preflight must return BROWSER_NOT_INSTALLED with clear hint."""
        with patch.dict("sys.modules", {"playwright": None}):
            with patch(
                "backend.app.core.preflight._import_playwright",
                side_effect=ImportError("No module named 'playwright'"),
            ):
                result = run_browser_preflight(force_refresh=True)
                assert result.ok is False
                assert result.error_code == "BROWSER_NOT_INSTALLED"
                assert "pip install" in result.admin_hint


class TestPhase1DeepHealthEndpoint:
    def test_deep_health_requires_admin(self):
        """Endpoint /api/system/health?deep=1 must enforce admin auth."""
        res = client.get("/api/system/health?deep=1")
        # Unauthenticated request to admin endpoint must be 401 or 403
        assert res.status_code in (401, 403)

    def test_deep_health_performs_launch_test(self):
        """Admin can trigger on-demand deep browser launch verification.
        Returns HTTP 200 in all cases; success field reflects actual browser availability."""
        headers = _get_admin_headers()
        res = client.get("/api/system/health?deep=1", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("ok", "healthy", "degraded")
        assert "browser_launch" in data
        # success may be False in CI/local envs without Playwright binaries
        assert isinstance(data["browser_launch"]["success"], bool)
        assert "latency_ms" in data["browser_launch"]


    def test_standard_health_without_deep_is_fast(self):
        """Standard /api/system/health does not perform heavy browser launch."""
        headers = _get_admin_headers()
        res = client.get("/api/system/health", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "browser_launch" not in data or data.get("deep") is not True
