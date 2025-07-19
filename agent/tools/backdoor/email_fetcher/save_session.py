# save_twitter_session.py

from playwright.sync_api import sync_playwright
import time
import json

def save_session():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print("\n🔐 Log in to Twitter manually in the browser window.")
        page.goto("https://twitter.com/login")
        time.sleep(60)  # give yourself time to log in

        # Save cookies and local storage
        storage = context.storage_state()
        with open("twitter_session.json", "w") as f:
            json.dump(storage, f)

        print("✅ Session saved.")
        browser.close()

if __name__ == "__main__":
    save_session()
