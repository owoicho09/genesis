import os
import sys
import re
import time
import csv
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import sys

# Add the project root to PYTHONPATH
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django
django.setup()

from agent.models import Lead  # Replace 'agent' with your actual app name if different

EMAIL_REGEX = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

ENHANCED_DORKS = [
    '"{niche}" site:about.me "@gmail.com"',
    '"{niche}" site:behance.net "@gmail.com"',
    '"{niche}" site:dribbble.com "contact" "@gmail.com"',
    '"{niche}" site:github.com "@gmail.com"',
    '"{niche}" inurl:contact "@gmail.com"',
    '"{niche}" inurl:about "@gmail.com"',
    '"{niche}" "contact me" "@gmail.com"',
    '"{niche}" inurl:blog "@gmail.com"',
    '"{niche}" "work with me" "@gmail.com"',
    '"{niche}" "email me" "@gmail.com"',
]

def duckduckgo_search(query, max_results=10):
    query = query.replace(" ", "+")
    url = f"https://html.duckduckgo.com/html/?q={query}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        links = []
        for a in soup.find_all('a', attrs={'class': 'result__url'}, href=True):
            href = a['href']
            if href.startswith("http"):
                links.append(href)
            if len(links) >= max_results:
                break
        return links
    except Exception as e:
        print(f"❌ DuckDuckGo search failed: {e}")
        return []

class DuckDorkScraper:
    def __init__(self, niche, location=None, limit=10):
        self.niche = niche
        self.location = location
        self.limit = limit
        self.scraped_leads = []

    def run(self):
        print(f"\n🔍 Scraping DuckDuckGo for: {self.niche}")
        for dork in ENHANCED_DORKS:
            query = dork.format(niche=self.niche)
            if self.location:
                query += f" site:{self.location}"
            print(f"\n🌐 Query: {query}")

            urls = duckduckgo_search(query, max_results=self.limit)
            for url in urls:
                print(f"➡️ Visiting: {url}")
                try:
                    res = requests.get(url, headers=HEADERS, timeout=10)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    text = soup.get_text()
                    emails = re.findall(EMAIL_REGEX, text)
                    for email in set(emails):
                        self.save_lead(email, url)
                except Exception as e:
                    print(f"⚠️ Error visiting {url}: {e}")
                time.sleep(2)

    def save_lead(self, email, source_url):
        username = email.split('@')[0]
        lead, created = Lead.objects.get_or_create(
            email=email,
            defaults={
                'username': username,
                'niche': self.niche,
                'source_url': source_url,
                'status': 'scraped'
            }
        )
        if created:
            print(f"✅ Saved: {email}")
            self.scraped_leads.append({
                'username': username,
                'email': email,
                'niche': self.niche,
                'source_url': source_url
            })
        else:
            print(f"⚠️ Already exists: {email}")

    def export_csv(self, path):
        if not self.scraped_leads:
            print("⚠️ No new leads to export.")
            return

        try:
            with open(path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['username', 'email', 'niche', 'source_url'])
                writer.writeheader()
                for lead in self.scraped_leads:
                    writer.writerow(lead)
            print(f"📁 Exported leads to {path}")
        except Exception as e:
            print(f"❌ Failed to export CSV: {e}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DuckDuckGo Dork Email Scraper")
    parser.add_argument('--niche', required=True, help='Niche keyword')
    parser.add_argument('--limit', type=int, default=10, help='Search result limit per dork')
    parser.add_argument('--location', help='Country TLD like .ng or .uk')
    parser.add_argument('--export', help='CSV output path')
    args = parser.parse_args()

    scraper = DuckDorkScraper(niche=args.niche, location=args.location, limit=args.limit)
    scraper.run()

    if args.export:
        scraper.export_csv(args.export)