from playwright.sync_api import sync_playwright
import time

def test_ui():
    print("Starting Playwright UI tests...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Navigating to http://localhost:5173/app/...")
        page.goto("http://localhost:5173/app/")
        time.sleep(3)
        
        print("Waiting for login page...")
        page.wait_for_selector("#login-username", timeout=10000)
        print("Logging in as dysp1...")
        page.locator("#login-username").fill("dysp1")
        page.locator("#login-password").fill("demo1234")
        page.locator("button[type='submit']").click()
        time.sleep(2)
        page.wait_for_load_state("networkidle")

        print("Verifying dashboard structure...")
        page.wait_for_selector("textarea, input[type='text']", timeout=10000)
        h1_text = page.locator("h1").first.inner_text()
        print(f"Header Text found: '{h1_text}'")
        assert "CIS" in h1_text or "KSP" in h1_text
        
        # Type a query
        print("Submitting a test query...")
        input_box = page.locator("textarea, input[type='text']").first
        input_box.fill("Find associates of Ravi Kumar in Koramangala")
        
        # Click send
        page.locator("button[type='submit'], button.action-btn.primary").first.click()
        
        # Wait for SSE responses
        print("Waiting for response stream...")
        
        # Wait for the status pill to appear and then disappear (meaning streaming is done)
        page.wait_for_selector(".status-pill", timeout=5000)
        page.wait_for_selector(".status-pill", state="hidden", timeout=45000)
        
        assistant_messages = page.locator(".message.assistant")
        count = assistant_messages.count()
        last_message = assistant_messages.nth(count - 1).inner_text()
        
        print("Last assistant message contents:")
        print(last_message)
        
        assert "evidence" in last_message.lower() or "mock" in last_message.lower(), "Response missing expected mock data"
        
        print("✅ UI E2E test passed successfully!")
        browser.close()

if __name__ == "__main__":
    test_ui()
