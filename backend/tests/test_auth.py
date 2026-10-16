"""
Authentication and Rate Limiting Tests.
"""

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings

client = TestClient(app)


def test_login_success():
    """Test successful login with admin credentials returns token and cookie."""
    res = client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "token" in data
    assert "csrf_token" in data
    assert data["username"] == settings.ADMIN_USERNAME
    assert data["role"] == "admin"
    assert settings.SESSION_COOKIE_NAME in res.cookies


def test_login_invalid_password():
    """Test login with wrong password fails with 401."""
    res = client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": "wrong-password-xyz"},
    )
    assert res.status_code == 401
    data = res.json()
    assert "Invalid username or password" in data["detail"]


def test_bearer_token_auth():
    """Test that Authorization: Bearer <token> allows accessing protected endpoints."""
    # 1. Login to get token
    login_res = client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    token = login_res.json()["token"]

    # 2. Access /api/auth/me using Bearer token without cookies
    auth_client = TestClient(app)
    res = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["username"] == settings.ADMIN_USERNAME
    assert res.json()["role"] == "admin"
