from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:8000/login')
    page.locator("input[placeholder*='admin']").fill('admin')
    import os
    page.locator("input[type='password']").fill(os.getenv("ADMIN_PASSWORD", "testAdminPass123!"))
    page.locator("button[type='submit']").click()
    page.wait_for_timeout(2000)
    print('Logged in, URL is:', page.url)
    
    # Try clicking the nav link or goto
    sessions_link = page.locator("a[href='/sessions']")
    if sessions_link.count() > 0:
        print('Found sessions link in sidebar, clicking it...')
        sessions_link.first.click()
    else:
        print('Sessions link not found, using goto...')
        page.goto('http://localhost:8000/sessions')
    
    time.sleep(2)
    print('Current URL:', page.url)
    page.screenshot(path='data/screenshots/debug_sessions.png')
    buttons = [b.inner_text() for b in page.locator('button').all()]
    print('Buttons on page:', buttons)
    browser.close()
