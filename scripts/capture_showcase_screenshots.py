import sys
import time
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(r"c:\Users\Sakshi\Desktop\Naukri\v8\naukri-job\docs\screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def capture_all():
    # 1. Login via backend API to get session token
    print("Authenticating admin session via API...", flush=True)
    admin_p = os.getenv("ADMIN_PASSWORD", "testAdminPass123!")
    res = requests.post(
        "http://127.0.0.1:8000/api/auth/login",
        json={"username": "admin", "password": admin_p},
        timeout=10
    )
    if res.status_code != 200:
        print(f"Auth failed: {res.text}", flush=True)
        return
    token = res.json()["token"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1.25  # Crisp retina-like rendering
        )

        # 0. Landing Page (Public - clean context)
        p0 = context.new_page()
        p0.goto("http://127.0.0.1:8000/landing", wait_until="domcontentloaded", timeout=12000)
        p0.wait_for_timeout(1000)
        p0.screenshot(path=str(OUTPUT_DIR / "00_landing_page.png"))
        p0.close()
        print("Captured 00_landing_page.png", flush=True)

        # 1. Login Page (Public)
        p1 = context.new_page()
        p1.goto("http://127.0.0.1:8000/login", wait_until="domcontentloaded", timeout=12000)
        p1.wait_for_timeout(1000)
        p1.screenshot(path=str(OUTPUT_DIR / "01_login_page.png"))
        p1.close()
        print("Captured 01_login_page.png", flush=True)

        # Inject session cookie and local/session storage for all protected pages
        context.add_cookies([
            {"name": "naukri_dashboard_session", "value": token, "domain": "127.0.0.1", "path": "/"}
        ])
        context.add_init_script(f"""
            localStorage.setItem('bot_auth_token', '{token}');
            sessionStorage.setItem('bot_auth_token', '{token}');
            sessionStorage.setItem('bot_user_claims', JSON.stringify({{
                username: 'admin',
                role: 'admin',
                is_admin: true,
                csrf_token: '{token}'
            }}));
        """)

        def take_shot(path_url: str, filename: str, delay: float = 1.0, scroll_y: int = 0):
            page = context.new_page()
            try:
                page.goto(f"http://127.0.0.1:8000{path_url}", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(int(delay * 1000))
                if scroll_y > 0:
                    page.evaluate(f"() => {{ const el = document.querySelector('main') || window; if (el.scrollTo) el.scrollTo(0, {scroll_y}); else el.scrollTop = {scroll_y}; }}")
                    page.wait_for_timeout(800)
                page.screenshot(path=str(OUTPUT_DIR / filename))
                print(f"Captured {filename}", flush=True)
            except Exception as e:
                print(f"Error capturing {filename}: {e}", flush=True)
            finally:
                page.close()

        # 2. Dashboard Top (HUD)
        take_shot("/dashboard", "02_dashboard_hud.png", delay=1.5)

        # 3. Dynamic Fresh Priority Interaction & Capture
        # Let's open dashboard and ensure the dynamic fresh filter displays cleanly
        dp = context.new_page()
        dp.goto("http://127.0.0.1:8000/dashboard", wait_until="networkidle", timeout=15000)
        dp.wait_for_timeout(1500)
        try:
            # Check toggle switches
            switches = dp.query_selector_all('button[role="switch"]')
            for s in switches:
                # If switch is off, toggle it on to demonstrate active dynamic filter in screenshot
                if "bg-zinc-800" in (s.get_attribute("class") or ""):
                    s.click()
                    dp.wait_for_timeout(500)
        except Exception as e:
            print(f"Toggle interaction note: {e}", flush=True)
        dp.evaluate("() => { const el = document.querySelector('main') || window; if (el.scrollTo) el.scrollTo(0, 360); else el.scrollTop = 360; }")
        dp.wait_for_timeout(800)
        dp.screenshot(path=str(OUTPUT_DIR / "03_dashboard_saas_grid.png"))
        dp.screenshot(path=str(OUTPUT_DIR / "03b_fresh_priority_dynamic.png"))
        print("Captured 03_dashboard_saas_grid.png & 03b_fresh_priority_dynamic.png", flush=True)
        dp.close()

        # 5. Live Activity Route
        take_shot("/activity", "05_live_activity.png", delay=1.2)

        # 7. Connected Accounts Route
        take_shot("/sessions", "07_auth_sessions.png", delay=1.2)

        # 8. Career Profile & Resume Route
        take_shot("/profile", "08_profile_and_resume.png", delay=1.2)

        # 9. Settings Route
        take_shot("/settings", "09_settings_and_pacing.png", delay=1.2)

        # 10. Admin Users Route
        take_shot("/admin/users", "10_admin_users.png", delay=1.2)

        # 6. Live Browser View Route (CDP Canvas)
        take_shot("/browser", "06_live_browser_view.png", delay=2.0)

        # 4. Remote Screencast Modal
        mp = context.new_page()
        try:
            mp.goto("http://127.0.0.1:8000/dashboard", wait_until="domcontentloaded", timeout=15000)
            mp.wait_for_timeout(1000)
            insp_btn = mp.query_selector('button:has-text("Inspect")')
            if insp_btn:
                insp_btn.click()
                mp.wait_for_timeout(1200)
                mp.screenshot(path=str(OUTPUT_DIR / "04_screencast_modal.png"))
                print("Captured 04_screencast_modal.png", flush=True)
        except Exception as e:
            print(f"Modal notice: {e}", flush=True)
        finally:
            mp.close()

        browser.close()
        print(f"\nAll showcase screenshots successfully refreshed in: {OUTPUT_DIR}", flush=True)

if __name__ == "__main__":
    capture_all()
