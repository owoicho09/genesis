import os
import subprocess
import json
import re
import requests
import sys
import django
from bs4 import BeautifulSoup
# Setup Django
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
import django
django.setup()

from agent.models import Lead

# === Constants ===
EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
HEADERS = {"User-Agent": "Mozilla/5.0"}
PYTHON_312_PATH = r"C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe"
CERT_PATH = r"C:\Users\HP\AppData\Local\Programs\Python\Python312\Lib\site-packages\certifi\cacert.pem"
# twitter_browser_scraper.py

from playwright.sync_api import sync_playwright
import re
import time




def extract_emails(text):
    return re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)

def scrape_twitter_leads(keyword, max_profiles=10):
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        # Load session
        with open("twitter_session.json", "r") as f:
            storage = json.load(f)
        context = browser.new_context(storage_state=storage)

        page = context.new_page()
        query = keyword.replace(' ', '%20')
        page.goto(f"https://twitter.com/search?q={query}&src=typed_query&f=user")
        time.sleep(5)

        profiles = page.query_selector_all('div[role="listitem"]')[:max_profiles]

        for profile in profiles:
            try:
                username = profile.query_selector('div[dir="ltr"] span').inner_text()
                name = profile.query_selector('div[dir="auto"] span').inner_text()
                bio = profile.inner_text()
                emails = extract_emails(bio)

                results.append({
                    'name': name,
                    'username': username,
                    'bio': bio,
                    'emails': emails
                })
            except Exception:
                continue

        browser.close()

    return results


if __name__ == "__main__":
    keywords = [
        "fitness coach",
        "branding expert",
        "nutritionist",
        "startup mentor",
        "copywriter for coaches"
    ]

    for keyword in keywords:
        print(f"\n🔍 Scraping leads for: {keyword}")
        leads = scrape_twitter_leads(keyword)

        if not leads:
            print("❌ No leads found.")
        else:
            for lead in leads:
                print(f"\n✅ @{lead['username']} — {lead['name']}")
                print(f"📜 Bio: {lead['bio']}")
                if lead['emails']:
                    print(f"📧 Email(s): {', '.join(lead['emails'])}")
                else:
                    print("📧 No email found.")
