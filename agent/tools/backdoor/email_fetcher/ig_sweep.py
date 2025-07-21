import os, csv, time, re, random, sys, json, asyncio
from urllib.parse import unquote, urlparse, parse_qs
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from django.core.exceptions import ValidationError
from django.db import transaction
import threading
from concurrent.futures import ThreadPoolExecutor

# Django Setup
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

try:
    import django

    django.setup()
    from agent.models import Lead  # Replace 'your_app' with your actual app name

    print("Django setup successful")
except Exception as e:
    print(f"❌ Django setup failed: {e}")
    sys.exit(1)

# Constants
INPUT_CSV = os.path.abspath(os.path.join(os.path.dirname(__file__), "csv-json/ig_profiles_v2.csv"))
OUTPUT_CSV = os.path.abspath(os.path.join(os.path.dirname(__file__), "csv-json/ig_profiles_data.csv"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/537.36 Chrome/113.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0"
]

SKIP_DOMAINS = {
    "instagram.com", "facebook.com", "about.instagram.com", "help.instagram.com",
    "privacycenter.instagram.com", "meta.com", "threads.net", "developers.facebook.com",
    "fb.com", "m.facebook.com", "business.facebook.com", "transparency.fb.com"
}

# Enhanced email regex with better validation
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

# Common bio link patterns
BIO_LINK_PATTERNS = [
    r'linktree\.com/[\w.-]+',
    r'linktr\.ee/[\w.-]+',
    r'bio\.link/[\w.-]+',
    r'beacons\.ai/[\w.-]+',
    r'carrd\.co/[\w.-]+',
    r'solo\.to/[\w.-]+',
    r'lnk\.bio/[\w.-]+',
    r'allmylinks\.com/[\w.-]+',
    r'linkby\.com/[\w.-]+',
    r'tap\.bio/[\w.-]+'
]


def read_profile_urls():
    """Read Instagram profile URLs from CSV file with better error handling"""
    urls = []
    try:
        with open(INPUT_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("Instagram Profile URL", "").strip()
                niche = row.get("Niche", "").strip()

                # Clean and validate URL
                if url and ("instagram.com/" in url):
                    # Ensure proper format
                    if not url.startswith("https://"):
                        url = "https://" + url.lstrip("http://")

                    # Extract username and rebuild clean URL
                    username = url.split("instagram.com/")[-1].split("/")[0].split("?")[0]
                    if username and username not in ["", "p", "reel", "stories", "tv"]:
                        clean_url = f"https://www.instagram.com/{username}/"
                        urls.append((niche, clean_url, username))

    except FileNotFoundError:
        print(f"❌ Error: Input file {INPUT_CSV} not found")
        return []
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return []

    print(f"📦 Successfully loaded {len(urls)} valid profile URLs")
    return urls


def is_valid_external_link(link):
    """Enhanced validation for external links"""
    if not link or not isinstance(link, str):
        return False

    try:
        # Clean the URL
        link = link.strip()
        if not link:
            return False

        # Add protocol if missing
        if not link.startswith(('http://', 'https://')):
            link = 'https://' + link

        parsed = urlparse(link)
        domain = parsed.netloc.replace("www.", "").lower()

        # Skip if no domain
        if not domain:
            return False

        # Skip blocked domains
        if any(skip_domain in domain for skip_domain in SKIP_DOMAINS):
            return False

        # Skip Instagram internal paths
        if 'instagram.com' in domain and any(
                path in parsed.path for path in ['/p/', '/reel/', '/stories/', '/tv/', '/explore/']):
            return False

        # Must have valid TLD
        if '.' not in domain or domain.endswith('.'):
            return False

        return True

    except Exception:
        return False


def extract_final_url(raw_url):
    """Extract final URL from Instagram redirectors and other URL shorteners"""
    if not raw_url:
        return raw_url

    try:
        # Handle Instagram's redirector: l.instagram.com/?u=...
        if "l.instagram.com" in raw_url:
            parsed = urlparse(raw_url)
            qs = parse_qs(parsed.query)
            if "u" in qs and qs["u"]:
                return unquote(qs["u"][0])

        # Handle other common redirectors
        if any(redirect in raw_url for redirect in ['t.co/', 'bit.ly/', 'tinyurl.com/', 'goo.gl/']):
            # For now, return as-is (could implement redirect following)
            return raw_url

        return raw_url

    except Exception:
        return raw_url


def wait_for_page_load(page, timeout=10000):
    """Wait for page to load with multiple strategies"""
    try:
        # Wait for network to be idle
        page.wait_for_load_state("networkidle", timeout=timeout)

        # Wait for main content
        page.wait_for_selector("main", timeout=5000)

        # Additional wait for dynamic content
        page.wait_for_timeout(2000)

        return True
    except:
        try:
            # Fallback: just wait for DOM
            page.wait_for_load_state("domcontentloaded", timeout=timeout)
            page.wait_for_timeout(3000)
            return True
        except:
            return False


def dismiss_popups(page):
    """Dismiss various Instagram popups and overlays"""
    popup_selectors = [
        "div[role=dialog] button",
        "button:has-text('Not Now')",
        "button:has-text('Not now')",
        "button:has-text('Maybe Later')",
        "button:has-text('Cancel')",
        "[aria-label='Close']",
        "div._ac69 button",
        "div[role=dialog] div[role=button]"
    ]

    for selector in popup_selectors:
        try:
            element = page.locator(selector).first
            if element.is_visible(timeout=1000):
                element.click(timeout=1000)
                page.wait_for_timeout(500)
                print("   ❌ Dismissed popup")
                break
        except:
            continue


def extract_bio_section_data(page):
    """Extract comprehensive bio section data with multiple fallback strategies"""
    print("   🔍 Extracting bio section data...")

    bio_data = {
        "name": "",
        "title": "",
        "bio": "",
        "external_links": set(),
        "emails": set(),
        "follower_count": "",
        "following_count": "",
        "post_count": ""
    }

    # Strategy 1: Try specific selectors for bio elements
    bio_selectors = [
        # Name/title selectors
        ("name", ["h2._aacl", "h1._aacl", "span._aacl._aaco._aacw._aacx._aad7._aade",
                  "div._ap3a._aaco._aacu._aacy._aad6._aade"]),
        # Bio text selectors
        ("bio", ["div._ac69", "span._ap3a._aaco._aacu._aacx._aad7._aade", "div.-vDIg span", "span[dir=auto]"]),
        # Stats selectors
        ("stats", ["div._ac7v", "ul._ac7v", "div._ac2a"])
    ]

    # Extract name/title
    try:
        name = page.locator("header section h1, header section h2, header section span[dir='auto']").first
        if name.is_visible(timeout=3000):
            bio_data["name"] = name.text_content().strip()
            print(f"   👤 Name: {bio_data['name']}")
    except:
        pass


    # Extract bio text
    bio_found = False
    try:
        # Instagram bio container is usually the first few <div>s inside header
        bio_container = page.locator("header section div:not([class])").all()

        for div in bio_container:
            text = div.text_content().strip()
            if text and len(text) > 15 and not text.startswith("@"):  # Filter out mentions
                bio_data["bio"] = text
                print(f"   📝 Bio: {text[:100]}...")
                bio_found = True
                break
    except:
        pass

    # Extract links from bio area only
    bio_area_selectors = [
        "section main div a[href]",
        "div._ac69 a[href]",
        "article div a[href]",
        "main section a[href]"
    ]

    for selector in bio_area_selectors:
        try:
            links = page.locator(selector)
            for i in range(links.count()):
                try:
                    link = links.nth(i)
                    href = link.get_attribute("href")
                    if href:
                        # Check if link is in bio area (not in posts)
                        box = link.bounding_box()
                        if box and box['y'] < 600:  # Approximate bio area
                            clean_url = extract_final_url(href.strip())
                            if is_valid_external_link(clean_url):
                                bio_data["external_links"].add(clean_url)
                except:
                    continue
        except:
            continue

    # Extract emails from bio text and visible elements
    bio_text = bio_data["bio"]
    if bio_text:
        emails = EMAIL_REGEX.findall(bio_text)
        for email in emails:
            if email.lower() not in ['@instagram.com', '@facebook.com']:
                bio_data["emails"].add(email.lower())

    # Also check for emails in link text content
    try:
        bio_area = page.locator("section main").first
        if bio_area.is_visible():
            full_text = bio_area.text_content()
            if full_text:
                emails = EMAIL_REGEX.findall(full_text)
                for email in emails:
                    if email.lower() not in ['@instagram.com', '@facebook.com']:
                        bio_data["emails"].add(email.lower())
    except:
        pass

    # Log results
    print(f"   🔗 External links found: {len(bio_data['external_links'])}")
    if bio_data["external_links"]:
        for link in list(bio_data["external_links"])[:3]:  # Show first 3
            print(f"      → {link}")

    print(f"   ✉️ Emails found: {len(bio_data['emails'])}")
    if bio_data["emails"]:
        for email in bio_data["emails"]:
            print(f"      → {email}")

    return bio_data


def save_to_database(bio_data, niche, username, instagram_url):
    """Save scraped data to Django Lead model - runs in separate thread"""
    print(f"   💾 Saving to database...")

    saved_leads = []

    def _save_to_db():
        try:
            with transaction.atomic():
                # Convert external_links set to string for storage
                external_urls_str = " | ".join(bio_data["external_links"]) if bio_data["external_links"] else ""

                # If there are emails, create a lead for each email
                if bio_data["emails"]:
                    for email in bio_data["emails"]:
                        try:
                            # Check if lead with this email already exists
                            existing_lead = Lead.objects.filter(email=email).first()

                            if existing_lead:
                                print(f"   ⚠️ Lead with email {email} already exists, updating...")
                                # Update existing lead
                                existing_lead.username = username
                                existing_lead.niche = niche or existing_lead.niche
                                existing_lead.source_url = instagram_url
                                existing_lead.source_name = "Instagram"
                                existing_lead.bio = bio_data["bio"]
                                existing_lead.external_urls = external_urls_str  # Save external URLs
                                existing_lead.save()
                                saved_leads.append(existing_lead)
                            else:
                                # Create new lead
                                lead = Lead.objects.create(
                                    username=username,
                                    email=email,
                                    niche=niche,
                                    source_url=instagram_url,
                                    source_name="Instagram",
                                    bio=bio_data["bio"],
                                    external_urls=external_urls_str  # Save external URLs
                                )
                                saved_leads.append(lead)
                                print(f"   ✅ Created new lead: {email}")

                        except ValidationError as e:
                            print(f"   ❌ Validation error for email {email}: {e}")
                            continue
                        except Exception as e:
                            print(f"   ❌ Error saving lead for email {email}: {e}")
                            continue

                else:
                    # No emails found, create a lead with username as identifier
                    # Use a placeholder email format or handle differently based on your needs
                    placeholder_email = None

                    try:
                        existing_lead = Lead.objects.filter(username=username, source_name="Instagram").first()

                        if existing_lead:
                            print(f"   ⚠️ Lead with username {username} already exists, updating...")
                            existing_lead.niche = niche or existing_lead.niche
                            existing_lead.source_url = instagram_url
                            existing_lead.bio = bio_data["bio"]
                            existing_lead.external_urls = external_urls_str  # Save external URLs
                            existing_lead.save()
                            saved_leads.append(existing_lead)
                        else:
                            # Create lead without email (you might want to modify your model to make email optional)
                            lead = Lead.objects.create(
                                username=username,
                                email=placeholder_email,  # You might want to make this field optional
                                niche=niche,
                                source_url=instagram_url,
                                source_name="Instagram",
                                bio=bio_data["bio"],
                                external_urls=external_urls_str  # Save external URLs
                            )
                            saved_leads.append(lead)
                            print(f"   ✅ Created new lead without email: {username}")

                    except Exception as e:
                        print(f"   ❌ Error saving lead for username {username}: {e}")

        except Exception as e:
            print(f"   ❌ Database transaction error: {e}")
            return []

        return saved_leads

    # Execute database operation in a thread to avoid async context issues
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_save_to_db)
            result = future.result(timeout=10)  # 10 second timeout
            return result
    except Exception as e:
        print(f"   ❌ Thread execution error: {e}")
        return []

def scrape_single_profile(page, niche, url, username):
    """Scrape a single Instagram profile with comprehensive error handling"""
    print(f"\n🔎 Scraping: {username} ({url})")

    try:
        # Navigate to profile
        page.goto(url, timeout=25000, wait_until="domcontentloaded")

        # Wait for page to load
        if not wait_for_page_load(page):
            print("   ⚠️ Page load timeout")
            return None

        # Dismiss popups
        dismiss_popups(page)

        # Check if profile exists
        if page.locator("span:has-text('Sorry, this page isn\\'t available')").is_visible():
            print("   ❌ Profile not found or private")
            return None

        # Extract bio data
        bio_data = extract_bio_section_data(page)

        # Save to database
        saved_leads = save_to_database(bio_data, niche, username, url)

        # Compile results for CSV
        result = {
            "Niche": niche,
            "Username": username,
            "Instagram URL": url,
            "Name": bio_data["name"],
            "Bio": bio_data["bio"],
            "External Links": " | ".join(bio_data["external_links"]) if bio_data["external_links"] else "",
            "Emails": " | ".join(bio_data["emails"]) if bio_data["emails"] else "",
            "Status": "Success",
            "DB_Saved": len(saved_leads)
        }

        print(f"   ✅ Successfully scraped {username} - Saved {len(saved_leads)} leads to DB")
        return result

    except PlaywrightTimeout:
        print("   ⚠️ Timeout error")
        return {
            "Niche": niche, "Username": username, "Instagram URL": url,
            "Name": "", "Bio": "", "External Links": "", "Emails": "", "Status": "Timeout", "DB_Saved": 0
        }
    except Exception as e:
        print(f"   ❌ Error: {str(e)[:100]}")
        return {
            "Niche": niche, "Username": username, "Instagram URL": url,
            "Name": "", "Bio": "", "External Links": "", "Emails": "", "Status": f"Error: {str(e)[:50]}", "DB_Saved": 0
        }


def scrape_profiles(profile_urls):
    """Main scraping function with improved browser management and enhanced pausing"""
    results = []

    with sync_playwright() as p:
        # Launch browser with better settings
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor"
            ]
        )

        # Create context with realistic settings
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York"
        )

        page = context.new_page()

        # Set additional headers
        page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        })

        success_count = 0
        db_saved_count = 0

        for index, (niche, url, username) in enumerate(profile_urls):
            print(f"\n📊 Progress: [{index + 1}/{len(profile_urls)}]")

            # Scrape profile with retries
            retries = 3
            result = None

            while retries > 0 and result is None:
                result = scrape_single_profile(page, niche, url, username)
                if result is None:
                    retries -= 1
                    if retries > 0:
                        print(f"   🔄 Retrying... ({retries} attempts left)")
                        time.sleep(random.uniform(3, 6))
                    else:
                        # Create failed result
                        result = {
                            "Niche": niche, "Username": username, "Instagram URL": url,
                            "Name": "", "Bio": "", "External Links": "", "Emails": "", "Status": "Failed", "DB_Saved": 0
                        }

            if result:
                results.append(result)
                if result["Status"] == "Success":
                    success_count += 1
                    db_saved_count += result.get("DB_Saved", 0)

            # Enhanced pause system
            # Every 3rd profile: 10 second pause
            if (index + 1) % 3 == 0:
                print(f"   🛑 Taking 10-second pause after 3 profiles...")
                time.sleep(10)

            # Regular delay between requests
            delay = random.uniform(3.5, 6.5)
            print(f"   ⏱️ Waiting {delay:.1f}s before next profile...")
            time.sleep(delay)

            # Extended break every 10 profiles
            if (index + 1) % 10 == 0:
                print("   🛑 Taking extended break...")
                time.sleep(random.uniform(15, 25))

        browser.close()

        print(f"\n📈 Scraping Summary:")
        print(f"   ✅ Successful: {success_count}")
        print(f"   ❌ Failed: {len(results) - success_count}")
        print(f"   📊 Total: {len(results)}")
        print(f"   💾 Database leads saved: {db_saved_count}")

    return results


def save_to_csv(results):
    """Save results to CSV with better formatting"""
    try:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["Niche", "Username", "Instagram URL", "Name", "Bio", "External Links", "Emails", "Status",
                          "DB_Saved"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in results:
                writer.writerow(result)

        print(f"\n💾 Successfully saved {len(results)} profiles to {OUTPUT_CSV}")

        # Print summary stats
        successful = sum(1 for r in results if r["Status"] == "Success")
        with_links = sum(1 for r in results if r["External Links"])
        with_emails = sum(1 for r in results if r["Emails"])
        total_db_saved = sum(r.get("DB_Saved", 0) for r in results)

        print(f"📊 Summary Stats:")
        print(f"   ✅ Successful scrapes: {successful}")
        print(f"   🔗 Profiles with external links: {with_links}")
        print(f"   ✉️ Profiles with emails: {with_emails}")
        print(f"   💾 Total leads saved to database: {total_db_saved}")

    except Exception as e:
        print(f"❌ Error saving to CSV: {e}")


def run_ig_sweep_scraper(profile_urls=None, save=True, print_summary=True):
    """Run the Instagram bio scraper with optional external URLs and save flag."""
    print("🚀 Enhanced Instagram Bio Scraper with Database Integration v2.1")
    print("=" * 60)

    # Test database connection
    try:
        lead_count = Lead.objects.count()
        if print_summary:
            print(f"📊 Current leads in database: {lead_count}")
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return []

    # Load URLs if not passed
    if profile_urls is None:
        profile_urls = read_profile_urls()

    if not profile_urls:
        print("❌ No valid profile URLs found. Exiting.")
        return []

    print(f"📦 Loaded {len(profile_urls)} profiles to scrape")
    print("⏱️ Pause schedule: 10s every 3 profiles + random delays")

    # Start scraping
    results = scrape_profiles(profile_urls)

    if results and save:
        save_to_csv(results)
        if print_summary:
            print(f"✅ Saved {len(results)} leads to CSV")
    elif not results:
        print("❌ No results to save")

    if print_summary:
        print("\n🎉 Scraping completed!")

    return results


if __name__ == "__main__":
    run_ig_sweep_scraper()
