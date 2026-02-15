from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            print("Navigating to http://localhost:3000")
            # Wait for vite to start
            for i in range(10):
                try:
                    page.goto("http://localhost:3000")
                    break
                except:
                    time.sleep(1)

            time.sleep(5) # Wait for app to hydrate

            # Take screenshot of the initial state
            page.screenshot(path="frontend_initial.png")
            print("Screenshot saved to frontend_initial.png")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
