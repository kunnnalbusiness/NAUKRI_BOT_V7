"""
User Isolation Tests.
Verifies that settings, counters, sessions, activity, and profiles are completely segregated between users,
and that new invited users get a 100% fresh dashboard and apply strictly using their own sessions.
"""

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.mongo import create_user, delete_user
from common.login_helper import check_session_status

client = TestClient(app)


def test_user_data_isolation():
    user1 = "isolated_user_alpha"
    user2 = "isolated_user_beta"
    passw = "securepass123"

    for u in (user1, user2):
        try:
            delete_user(u)
        except Exception:
            pass
        create_user(u, passw, role="user", delay_seconds=5)

    # Login as User 1
    res1 = client.post("/api/auth/login", json={"username": user1, "password": passw})
    token1 = res1.json()["token"]

    # Login as User 2
    res2 = client.post("/api/auth/login", json={"username": user2, "password": passw})
    token2 = res2.json()["token"]

    # User 1 sets delay to 12s
    client.post(
        "/api/user/settings",
        json={"delay_seconds": 12},
        headers={"Authorization": f"Bearer {token1}"},
    )

    # User 2 sets delay to 7s
    client.post(
        "/api/user/settings",
        json={"delay_seconds": 7},
        headers={"Authorization": f"Bearer {token2}"},
    )

    # Fetch User 1 settings
    s1 = client.get(
        "/api/user/settings", headers={"Authorization": f"Bearer {token1}"}
    ).json()
    assert s1["delay_seconds"] == 12

    # Fetch User 2 settings
    s2 = client.get(
        "/api/user/settings", headers={"Authorization": f"Bearer {token2}"}
    ).json()
    assert s2["delay_seconds"] == 7

    # Ensure new user counts start at 0
    assert s1["total_applied"] == 0
    assert s2["total_applied"] == 0

    # Cleanup
    delete_user(user1)
    delete_user(user2)


def test_new_invited_user_fresh_dashboard_and_own_login():
    """
    Verifies that:
    1. A newly invited user logging in sees a completely fresh dashboard:
       - 0 applications applied, 0 skipped, 0 total
       - Missing sessions for Naukri and LinkedIn
       - Incomplete profile warning
       - Stopped/Idle bot engines
       - Empty activity feed
       - No inherited admin sheet/webhook
    2. Starting the bot requires their own profile and session.
    3. Importing/saving session for this user does NOT affect other users.
    """
    invited_username = "fresh_invited_candidate"
    other_username = "other_test_user"
    passw = "validPass123"

    for u in (invited_username, other_username):
        try:
            delete_user(u)
        except Exception:
            pass

    # Admin creates invited user
    create_user(invited_username, passw, role="user", delay_seconds=5)
    create_user(other_username, passw, role="user", delay_seconds=5)

    # Log in as newly invited user
    res = client.post(
        "/api/auth/login", json={"username": invited_username, "password": passw}
    )
    assert res.status_code == 200
    token = res.json()["token"]
    csrf = res.json()["csrf_token"]
    headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}

    # 1. Check /api/status (Dashboard state)
    status_res = client.get("/api/status", headers=headers)
    assert status_res.status_code == 200
    status_data = status_res.json()

    # User metrics
    assert status_data["user"]["username"] == invited_username
    assert status_data["user"]["total_applied"] == 0
    assert status_data["user"]["is_admin"] is False

    # Profile completeness: incomplete for brand new user
    assert status_data["profile"]["is_complete"] is False

    # Sessions: strictly Missing
    assert status_data["sessions"]["naukri"]["status"] == "Missing"
    assert status_data["sessions"]["linkedin"]["status"] == "Missing"

    # Engines: stopped, idle, 0 counts
    assert status_data["engines"]["naukri"]["status"] == "Stopped"
    assert status_data["engines"]["naukri"]["session_applied_count"] == 0
    assert status_data["engines"]["linkedin"]["status"] == "Stopped"
    assert status_data["engines"]["linkedin"]["session_applied_count"] == 0

    # Activity: 0 stats, empty recent list
    assert status_data["activity"]["stats"]["total_applied"] == 0
    assert status_data["activity"]["stats"]["applied_today"] == 0
    assert len(status_data["activity"]["recent"]) == 0

    # Sheet settings: blank (never inherited from admin)
    assert status_data["sheet"]["sheet_url"] == ""
    assert status_data["sheet"]["webhook_url"] == ""

    # 2. Check /api/sessions
    sess_res = client.get("/api/sessions", headers=headers)
    assert sess_res.status_code == 200
    assert sess_res.json()["naukri"]["status"] == "Missing"
    assert sess_res.json()["linkedin"]["status"] == "Missing"

    # 3. Check /api/activity
    act_res = client.get("/api/activity", headers=headers)
    assert act_res.status_code == 200
    assert act_res.json()["stats"]["total_applied"] == 0
    assert act_res.json()["recent"] == []

    # 4. Attempt to start engine before profile is complete -> blocked
    start_fail_prof = client.post("/api/bot/naukri/start", json={}, headers=headers)
    assert start_fail_prof.status_code == 400
    assert "profile" in start_fail_prof.json()["detail"].lower()

    # Complete the profile with an existing dummy resume PDF
    from common.paths import RESUMES_DIR

    dummy_resume = RESUMES_DIR / f"{invited_username}_resume.pdf"
    dummy_resume.parent.mkdir(parents=True, exist_ok=True)
    dummy_resume.write_bytes(b"%PDF-1.4 dummy pdf resume content")

    profile_payload = {
        "full_name": "Fresh Candidate",
        "current_city": "Bengaluru",
        "total_experience_years": 3,
        "target_roles": ["Backend Developer"],
        "notice_period_days": 15,
        "current_ctc_lpa": 10.0,
        "expected_ctc_lpa": 14.0,
        "resume_path": str(dummy_resume),
    }
    prof_res = client.post("/api/profile", json=profile_payload, headers=headers)
    assert prof_res.status_code == 200
    assert prof_res.json()["is_complete"] is True

    # Attempt to start engine without session -> blocked with session missing
    start_fail_sess = client.post("/api/bot/naukri/start", json={}, headers=headers)
    assert start_fail_sess.status_code == 400
    assert "session" in start_fail_sess.json()["detail"].lower()

    # Import session for this user
    mock_session = {
        "cookies": [
            {
                "name": "nauk_at",
                "value": "dummy_naukri_token",
                "domain": ".naukri.com",
                "path": "/",
            }
        ],
        "origins": [],
    }
    import_res = client.post(
        "/api/sessions/naukri/import", json=mock_session, headers=headers
    )
    assert import_res.status_code == 200
    assert import_res.json()["success"] is True

    # Verify session is now Valid for this user
    chk = check_session_status(
        "naukri", force_live_check=False, username=invited_username
    )
    assert chk["status"] == "Valid"
    assert chk["present"] is True

    # Verify session remains Missing for the other user!
    chk_other = check_session_status(
        "naukri", force_live_check=False, username=other_username
    )
    assert chk_other["status"] == "Missing"

    # Cleanup
    delete_user(invited_username)
    delete_user(other_username)
