from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome', headless=True)
    ctx = b.new_context(viewport={'width': 1280, 'height': 800})
    page = ctx.new_page()
    page.goto('https://www.naukri.com/nlogin/login', wait_until='domcontentloaded')
    time.sleep(2)
    for inp in page.locator('input').all():
        ph = inp.get_attribute('placeholder') or ''
        tp = inp.get_attribute('type') or ''
        bx = inp.bounding_box()
        print(f"type={tp}, placeholder='{ph}', bbox={bx}")
    b.close()
