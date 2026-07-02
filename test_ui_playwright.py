from playwright.sync_api import sync_playwright
import time

def test_ui():
    print("Starting Playwright UI tests...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Navigating to http://localhost:5173...")
        page.goto("http://localhost:5173")
        page.wait_for_load_state("networkidle")
        
        # Verify title or basic structure
        print("Verifying sidebar and header...")
        assert page.locator("h1").inner_text() == "PS-1 CIS"
        
        # Type a query
        print("Submitting a test query...")
        input_box = page.locator("input[type='text']")
        input_box.fill("Find associates of Ravi Kumar in Koramangala")
        
        # Click send
        page.locator("button.action-btn.primary").click()
        
        # Wait for SSE responses
        print("Waiting for response stream...")
        
        # Wait for the status pill to appear and then disappear (meaning streaming is done)
        page.wait_for_selector(".status-pill", timeout=5000)
        page.wait_for_selector(".status-pill", state="hidden", timeout=20000)
        
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
