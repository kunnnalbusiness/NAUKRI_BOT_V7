"""
Live API Benchmark and Endpoint Health Verification Script.
Reads credentials from environment variables / config instead of hardcoding.
"""
import os
import urllib.request
import json
import time

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", os.getenv("DASHBOARD_PASSWORD", "")).strip()

def run():
    print("--- 1. Testing /health API ---")
    t0 = time.perf_counter()
    with urllib.request.urlopen("http://localhost:8000/health") as resp:
        health_data = json.loads(resp.read().decode())
        health_time = (time.perf_counter() - t0) * 1000
    print(f"Health API Status: {health_data.get('database')} in {health_time:.1f}ms")

    print("\n--- 2. Testing /api/auth/login API ---")
    t0 = time.perf_counter()
    req = urllib.request.Request(
        "http://localhost:8000/api/auth/login",
        data=json.dumps({"username": ADMIN_USER, "password": ADMIN_PASS}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        login_data = json.loads(resp.read().decode())
        login_time = (time.perf_counter() - t0) * 1000
    token = login_data.get("token")
    print(f"Login API: Status 200, JWT token issued in {login_time:.1f}ms")

    print("\n--- 3. Testing POST /api/auth/ws-ticket API (One-Time Ticket) ---")
    t0 = time.perf_counter()
    req_ticket = urllib.request.Request(
        "http://localhost:8000/api/auth/ws-ticket",
        data=b"{}",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req_ticket) as resp:
        ticket_data = json.loads(resp.read().decode())
        ticket_time = (time.perf_counter() - t0) * 1000
    ticket = ticket_data.get("ticket")
    print(f"WS Ticket API: Success, ticket issued ({ticket[:16]}...) in {ticket_time:.1f}ms")

    print("\n--- 4. Testing GET /api/activity API ---")
    t0 = time.perf_counter()
    req_stats = urllib.request.Request(
        "http://localhost:8000/api/activity",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req_stats) as resp:
        stats_data = json.loads(resp.read().decode())
        stats_time = (time.perf_counter() - t0) * 1000
    print(f"Activity Stats API: Success in {stats_time:.1f}ms (Applied: {stats_data.get('applied_count')}, Skipped: {stats_data.get('skipped_count')})")

    print("\n--- 5. Testing Static SPA Index (Production Vite Build served by FastAPI) ---")
    t0 = time.perf_counter()
    with urllib.request.urlopen("http://localhost:8000/") as resp:
        html = resp.read().decode()
        spa_time = (time.perf_counter() - t0) * 1000
    print(f"FastAPI SPA Index: Status 200 ({len(html)} bytes) served in {spa_time:.1f}ms")

if __name__ == "__main__":
    run()
