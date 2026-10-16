"""
Role-Based Access Control (RBAC) and Admin Enforcement Tests.
"""

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.db.mongo import create_user, delete_user

client = TestClient(app)


def test_admin_access_allowed():
    """Verify admin has access to /api/admin/users."""
    login_res = client.post(
        "/api/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    token = login_res.json()["token"]

    res = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    users = res.json()
    assert isinstance(users, list)
    assert any(u["username"] == settings.ADMIN_USERNAME for u in users)


def test_regular_user_access_forbidden():
    """Verify regular user receives 403 Forbidden on admin endpoints."""
    # Ensure test regular user exists
    test_user = "test_regular_role_user"
    test_pass = "userpass123"
    try:
        delete_user(test_user)
    except Exception:
        pass
    create_user(test_user, test_pass, role="user")

    # Login as regular user
    login_res = client.post(
        "/api/auth/login", json={"username": test_user, "password": test_pass}
    )
    token = login_res.json()["token"]

    # Attempt to access admin endpoint
    res = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert "Admin privileges required" in res.json()["detail"]

    # Attempt to create user as non-admin
    res_create = client.post(
        "/api/admin/users",
        json={"username": "hacker_account", "password": "password123", "role": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_create.status_code == 403

    # Clean up
    delete_user(test_user)
