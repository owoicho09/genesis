import os, sys, re, time, csv, json, random
from bs4 import BeautifulSoup
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Django setup (if needed)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
import django
django.setup()

# === CONFIG ===
CSV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "csv-json/ig_profiles_v3.csv"))
OFFSETS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "csv-json/bing_offsets.json"))
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/537.36 Chrome/113.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/114.0.5735.110 Safari/537.36"
]

DORK_PATTERNS = [
    '"{niche}" site:instagram.com',
    '"{niche}" site:instagram.com "contact"',
    '"{niche}" site:instagram.com "gmail.com"',
    '"{niche}" site:instagram.com "email"',
    '"{niche}" site:instagram.com intitle:{niche}',
    # Specific sections or bio keywords
    '"{niche}" site:instagram.com intext:"link in bio"',
    '"{niche}" site:instagram.com intext:"DM for coaching"',
    '"{niche}" site:instagram.com intext:coach AND email',
    '"{niche}" site:instagram.com "online coaching" email',
    '"{niche}" site:instagram.com "fitness coach" "gmail.com"',

]

NICHES = [
    "fitness coach",
    "personal trainer",
    "yoga instructor",
    "online fitness coach",
    "nutrition coach"
]
PAGES_PER_BLOCK = 5
MAX_PROFILES_PER_RUN = 200


def load_existing_profiles():
    existing = set()
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.add(row["Instagram Profile URL"].strip())
    return existing


def load_offsets():
    return json.load(open(OFFSETS_FILE)) if os.path.exists(OFFSETS_FILE) else {}


def save_offsets(offsets):
    with open(OFFSETS_FILE, "w") as f:
        json.dump(offsets, f, indent=2)


def extract_instagram_urls(soup):
    results = set()
    for tag in soup.find_all(["cite", "a"], href=True):
        text = tag.get_text() if tag.name == "cite" else tag['href']
        match = re.search(r"https?://(www\.)?instagram\.com/([a-zA-Z0-9_.]+)", text)
        if match:
            username = match.group(2)
            if username.lower() not in ["p", "reel", "tv", "explore"]:
                results.add(f"https://www.instagram.com/{username}")
    return results


def bing_search(query, start_offset=0, pages=5):
    results = set()
    print(f"📌 Dork query: {query}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = context.new_page()


        # Force region and language to English US
        region_lang = "&mkt=en-US&setlang=en-US"

        for offset in range(start_offset, start_offset + pages * 10, 10):
            search_url = f"https://www.bing.com/search?q={quote(query)}&first={offset}{region_lang}"

            print(f"🔍 Searching: {search_url}")
            try:
                page.goto(search_url, timeout=20000, wait_until="networkidle")
                page.wait_for_timeout(2500)

                html = page.inner_html("body")

                # Match full profile URLs
                matches1 = re.findall(r'https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)', html)
                # Match relative hrefs like /trainername
                matches2 = re.findall(r'href=["\']/(?!p/|reel/|tv/|explore/)([a-zA-Z0-9_.]+)', html)

                for username in set(matches1 + matches2):
                    profile_url = f"https://www.instagram.com/{username}"
                    if username.lower() not in ["p", "reel", "tv", "explore"]:
                        results.add(profile_url)

                print(f"   → Extracted {len(results)} profiles from offset {offset}")

            except PlaywrightTimeout:
                print(f"⚠️ Timeout on: {search_url}")
            except Exception as e:
                print(f"❌ Error on {search_url} — {e}")
            time.sleep(1.2)

        browser.close()
    return list(results)


def save_new_to_csv(new_rows):
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Niche", "Instagram Profile URL"])
        for niche, url in new_rows:
            writer.writerow([niche, url])
            print(f"💾 Saved: [{niche}] {url}")
    print(f"\n✅ Total new profiles saved: {len(new_rows)}")


# === MAIN EXECUTION ===
def run_instagram_dork_scraper(niches=None, max_profiles=100):
    print("🚀 Starting Instagram Dork Scraper...\n")

    existing_profiles = load_existing_profiles()
    offsets = load_offsets()
    all_new_rows = []
    total_collected = 0

    # Default niches if not passed in
    if not niches:
        niches = NICHES

    for niche in niches:
        print(f"\n🔎 Dorking for niche: {niche}")
        for dork_template in DORK_PATTERNS:
            if total_collected >= max_profiles:
                break

            dork_key = f"{niche}||{dork_template}"
            start_offset = offsets.get(dork_key, 0)
            dork_query = dork_template.format(niche=niche)

            urls = bing_search(dork_query, start_offset=start_offset, pages=PAGES_PER_BLOCK)

            new_count = 0
            for url in urls:
                if url not in existing_profiles:
                    all_new_rows.append((niche, url))
                    existing_profiles.add(url)
                    new_count += 1
                    total_collected += 1
                    if total_collected >= max_profiles:
                        break

            print(f"➕ Found {len(urls)} profiles, {new_count} new for niche '{niche}' + dork '{dork_template}'")
            offsets[dork_key] = start_offset + PAGES_PER_BLOCK * 10

    if all_new_rows:
        save_new_to_csv(all_new_rows)
    else:
        print("📭 No new profiles to save.")

    save_offsets(offsets)
    print(f"📄 Updated offsets saved to {OFFSETS_FILE}")
    print("✅ Script completed.")

    return all_new_rows  # Return data for further use


if __name__ == "__main__":
    run_instagram_dork_scraper()
