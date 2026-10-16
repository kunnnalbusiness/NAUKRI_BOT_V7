"""
Phase 5 Tests: Engine ownership, mutual exclusion (busy status), stop permissions, and user profile isolation.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.db.mongo import create_user, delete_user, save_user_profile
from common.paths import RESUMES_DIR
from common.engine_manager import engine_manager
from common.profile import Profile

client = TestClient(app)


def _login(username, password):
    res = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert res.status_code == 200
    token = res.json()["token"]
    csrf = res.json().get("csrf_token", "")
    return {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}


class TestPhase5OwnershipAndIsolation:
    def test_non_admin_never_gets_admin_profile_yaml(self):
        """Profile.load_for_user must never return config/profile.yaml for non-admin users."""
        test_user = "phase5_isolated_candidate"
        try:
            delete_user(test_user)
        except Exception:
            pass
        create_user(test_user, "testpass123", role="user")

        # Without profile created in DB, it must raise ValueError and NOT return admin profile.yaml
        with pytest.raises(ValueError) as exc_info:
            Profile.load_for_user(test_user)
        assert "complete karo" in str(exc_info.value).lower()

        # Calling with None or empty string must raise ValueError
        with pytest.raises(ValueError):
            Profile.load_for_user(None)
        with pytest.raises(ValueError):
            Profile.load_for_user("")

        delete_user(test_user)

    def test_engine_ownership_and_busy_rejection(self):
        """When an engine is running for User A, User B must receive 409 Busy and cannot hijack or stop it."""
        user_a = "phase5_user_alice"
        user_b = "phase5_user_bob"
        passw = "testpass123"

        for u in (user_a, user_b):
            try:
                delete_user(u)
            except Exception:
                pass
            create_user(u, passw, role="user")
            # Create valid profile & dummy resume
            resume_file = RESUMES_DIR / f"{u}_resume.pdf"
            resume_file.parent.mkdir(parents=True, exist_ok=True)
            resume_file.write_bytes(b"%PDF-1.4 dummy resume")
            save_user_profile(
                u,
                {
                    "full_name": u.title(),
                    "current_city": "Delhi / NCR",
                    "total_experience_years": 4,
                    "target_roles": ["Data Engineer"],
                    "notice_period_days": 30,
                    "current_ctc_lpa": 12.0,
                    "expected_ctc_lpa": 18.0,
                    "resume_path": str(resume_file),
                },
            )

        headers_a = _login(user_a, passw)
        headers_b = _login(user_b, passw)
        admin_headers = _login(settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD)

        # Import mock session for user A
        mock_sess = {
            "cookies": [
                {
                    "name": "nauk_at",
                    "value": "val123",
                    "domain": ".naukri.com",
                    "path": "/",
                }
            ],
            "origins": [],
        }
        client.post("/api/sessions/naukri/import", json=mock_sess, headers=headers_a)
        client.post("/api/sessions/naukri/import", json=mock_sess, headers=headers_b)

        # 1. User A starts Naukri engine
        start_res = client.post("/api/bot/naukri/start", json={}, headers=headers_a)
        assert start_res.status_code == 200

        try:
            # 2. User B tries to start Naukri engine -> must get 409 Conflict with busy message
            busy_res = client.post("/api/bot/naukri/start", json={}, headers=headers_b)
            assert busy_res.status_code == 409
            assert "busy" in busy_res.json()["detail"].lower()
            assert user_a in busy_res.json()["detail"]

            # 3. User B tries to STOP User A's engine -> must get 403 Forbidden
            stop_unauth = client.post("/api/bot/naukri/stop", headers=headers_b)
            assert stop_unauth.status_code == 403

            # 4. User A (owner) CAN stop their engine
            stop_owner = client.post("/api/bot/naukri/stop", headers=headers_a)
            assert stop_owner.status_code == 200

            # 5. Now engine is free: User B can start
            start_b = client.post("/api/bot/naukri/start", json={}, headers=headers_b)
            assert start_b.status_code == 200

            # 6. Admin can stop any user's engine
            stop_admin = client.post("/api/bot/naukri/stop", headers=admin_headers)
            assert stop_admin.status_code == 200
        finally:
            engine_manager.stop_engine("naukri", is_admin=True)
            delete_user(user_a)
            delete_user(user_b)
