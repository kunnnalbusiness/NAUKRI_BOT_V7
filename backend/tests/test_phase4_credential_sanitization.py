"""
Phase 4 Tests: Zero-Leak Credential Sanitization and Production Password Enforcement.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import Settings, settings

client = TestClient(app)


def _login_admin():
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


class TestPhase4CredentialSanitization:
    def test_login_page_source_has_no_credentials_leak(self):
        """Frontend Login.tsx must never contain default credentials hint 'admin123'."""
        login_tsx = Path("frontend/src/pages/Login.tsx")
        assert login_tsx.exists()
        content = login_tsx.read_text(encoding="utf-8")
        assert (
            "admin123" not in content
        ), "Found leaked credential 'admin123' in Login.tsx!"
        assert (
            "Default Credentials" not in content
        ), "Found 'Default Credentials' banner in Login.tsx!"

    def test_production_mode_fails_if_admin_password_is_default(self):
        """In production environment, default admin password 'admin123' must trigger fatal error."""
        prod_settings = Settings(ENV="production", ADMIN_PASSWORD="admin123")
        with pytest.raises(RuntimeError) as exc_info:
            prod_settings.validate_setup()
        assert "ADMIN_PASSWORD" in str(exc_info.value)

    def test_api_responses_never_contain_password_keys(self):
        """Scans all critical endpoints to ensure password or password_hash is never exposed."""
        headers = _login_admin()

        # 1. /api/auth/me
        res = client.get("/api/auth/me", headers=headers)
        assert res.status_code == 200
        assert "password" not in res.json()
        assert "password_hash" not in res.json()

        # 2. /api/status
        res = client.get("/api/status", headers=headers)
        assert res.status_code == 200
        text = res.text.lower()
        assert "password_hash" not in text
        assert "mongodb+srv://" not in text

        # 3. /api/user/settings
        res = client.get("/api/user/settings", headers=headers)
        assert res.status_code == 200
        assert "password" not in res.json()
        assert "password_hash" not in res.json()

        # 4. /api/admin/users
        res = client.get("/api/admin/users", headers=headers)
        assert res.status_code == 200
        users = res.json()
        assert isinstance(users, list)
        for u in users:
            assert "password" not in u
            assert "password_hash" not in u

    def test_invite_member_response_does_not_echo_password(self):
        """Admin creating a new user must not return the plaintext password in response."""
        headers = _login_admin()
        test_user = "phase4_sanitize_test"

        # Cleanup if exists
        client.delete(f"/api/admin/users/{test_user}", headers=headers)

        res = client.post(
            "/api/admin/users",
            json={
                "username": test_user,
                "password": "SecretTestPassword99#",
                "role": "user",
                "delay_seconds": 5,
            },
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        user_info = data.get("user", {})
        assert "password" not in user_info
        assert "password_hash" not in user_info
        assert "SecretTestPassword99#" not in res.text

        # Cleanup
        client.delete(f"/api/admin/users/{test_user}", headers=headers)
