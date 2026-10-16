"""
API Automation Engine Start/Status/Stop Verification
Simulates exactly what the Web UI executes when 'Start' button is clicked:
1. Authenticates as admin
2. Retrieves initial engine status via GET /api/status
3. Calls POST /api/engine/linkedin/start
4. Polls real-time state machine progression
5. Gracefully stops engine via POST /api/engine/linkedin/stop
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

print("=" * 60)
print("1. AUTHENTICATION")
print("=" * 60)
admin_p = os.getenv("ADMIN_PASSWORD", "testAdminPass123!")
login_res = s.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": admin_p})
if login_res.status_code != 200:
    print(f"[ERROR] Login failed: {login_res.status_code} {login_res.text}")
    exit(1)

data = login_res.json()
token = data.get("token")
csrf = data.get("csrf_token")
headers = {
    "Authorization": f"Bearer {token}",
    "X-CSRF-Token": csrf or ""
}
print(f"Logged in as admin. Token: {'present' if token else 'missing'}")

print("\n" + "=" * 60)
print("2. INITIAL BOT STATUS")
print("=" * 60)
st_res = s.get(f"{BASE_URL}/api/status", headers=headers)
engines = st_res.json().get("engines", {})
li_init = engines.get("linkedin", {})
print(f"LinkedIn Initial State: Status={li_init.get('status')}, Reason='{li_init.get('reason')}'")

print("\n" + "=" * 60)
print("3. STARTING LINKEDIN ENGINE")
print("=" * 60)
start_res = s.post(f"{BASE_URL}/api/engine/linkedin/start", headers=headers, json={"only_fresh_10min": False})
print(f"HTTP Status: {start_res.status_code}, Response: {start_res.text}")

print("\n" + "=" * 60)
print("4. POLLING ENGINE STATUS (Next 3 seconds)")
print("=" * 60)
for i in range(1, 4):
    time.sleep(1)
    st_poll = s.get(f"{BASE_URL}/api/status", headers=headers)
    li_st = st_poll.json().get("engines", {}).get("linkedin", {})
    print(f"  +{i}s: Status='{li_st.get('status')}', Reason='{li_st.get('reason')}'")

print("\n" + "=" * 60)
print("5. STOPPING ENGINE CLEANUP")
print("=" * 60)
stop_res = s.post(f"{BASE_URL}/api/engine/linkedin/stop", headers=headers)
print(f"Stop HTTP Status: {stop_res.status_code}, Response: {stop_res.text}")
print("[DONE] Test complete.")
