"""
Test for Admin Password Rotation, Startup Sync, and Prior Token Invalidation.
Verifies that:
1. When DB is seeded with an old admin password, startup synchronizes the new ADMIN_PASSWORD.
2. Login with the old password fails (401 Unauthorized).
3. Login with the new password succeeds (200 OK).
4. Tokens issued prior to password rotation are revoked (token_version invalidated).
"""

import pytest
from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.security import hash_password, create_session_token
from backend.app.db.mongo import get_db, _read_local_store, _write_local_store, _LOCK, init_db, get_user

client = TestClient(app)


def test_admin_password_rotation_and_token_invalidation():
    admin_user = settings.ADMIN_USERNAME.strip().lower()
    old_password = "oldAdminPassword123"
    new_password = "brandNewSecretPassword999!"

    # 1. Seed DB / store with old password and token_version = 1
    old_hash = hash_password(old_password)
    db = get_db()
    if db is not None:
        db.users.update_one(
            {"username": admin_user},
            {"$set": {"password_hash": old_hash, "token_version": 1}},
            upsert=True,
        )
    with _LOCK:
        store = _read_local_store()
        store.setdefault("users", {})[admin_user] = {
            "username": admin_user,
            "password_hash": old_hash,
            "token_version": 1,
            "role": "admin",
            "status": "Active",
        }
        _write_local_store(store)

    # 2. Issue a token under the old password (token_version = 1)
    old_token, _ = create_session_token(admin_user, role="admin", token_version=1)

    # Verify old token works before rotation
    verify_res_old = client.get(
        "/api/admin/users", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert verify_res_old.status_code == 200

    # 3. Simulate new ADMIN_PASSWORD environment configuration & run startup init_db()
    original_pass = settings.ADMIN_PASSWORD
    try:
        settings.ADMIN_PASSWORD = new_password
        init_db()

        # 4. Old password login must fail
        login_old = client.post(
            "/api/auth/login", json={"username": admin_user, "password": old_password}
        )
        assert login_old.status_code == 401
        assert "invalid" in login_old.json()["detail"].lower()

        # 5. Old token must be rejected as revoked
        revoked_check = client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {old_token}"}
        )
        assert revoked_check.status_code == 401

        # 6. New password login must succeed
        login_new = client.post(
            "/api/auth/login", json={"username": admin_user, "password": new_password}
        )
        assert login_new.status_code == 200
        new_token = login_new.json()["token"]

        # 7. New token must allow access to admin routes
        verify_new = client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {new_token}"}
        )
        assert verify_new.status_code == 200
    finally:
        settings.ADMIN_PASSWORD = original_pass
        init_db()
