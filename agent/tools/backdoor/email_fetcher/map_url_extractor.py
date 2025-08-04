
import asyncio
from playwright.async_api import async_playwright
import django
import os,sys,re,csv
from urllib.parse import urljoin, urlparse
from asgiref.sync import sync_to_async

import time
import sys
sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")  # <- replace with your project
django.setup()
from agent.models import Lead  # <- replace with your app name
from agent.tools.utils.send_email_update import send_scraping_update

# Enhanced email regex patterns
EMAIL_PATTERNS = [
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    r'email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    r'contact[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
]

# Common pages to check for contact info
CONTACT_PAGES = [
    '/contact',
    '/contact-us',
    '/about',
    '/about-us',
    '/team',
    '/staff',
    '/get-in-touch',
    '/reach-out',
    '/connect',
    '/book',
    '/booking',
    '/consultation',
]


async def extract_emails_from_content(content):
    """Extract emails using multiple regex patterns"""
    print("    🔍 Starting email extraction from content...")
    emails = set()

    for i, pattern in enumerate(EMAIL_PATTERNS):
        print(f"    📧 Trying pattern {i + 1}: {pattern}")
        matches = re.findall(pattern, content, re.IGNORECASE)
        print(f"    📧 Pattern {i + 1} found {len(matches)} matches")

        if matches and isinstance(matches[0], tuple):
            pattern_emails = [match[0] for match in matches]
        else:
            pattern_emails = matches

        emails.update(pattern_emails)
        print(f"    📧 Pattern {i + 1} emails: {pattern_emails}")

    print(f"    📧 Total raw emails found: {len(emails)}")
    print(f"    📧 Raw emails: {list(emails)}")

    # Enhanced filtering - exclude common non-personal emails and error tracking
    filtered_emails = []
    exclude_patterns = [
        r'noreply@', r'no-reply@', r'info@', r'support@', r'hello@',
        r'admin@', r'webmaster@', r'postmaster@', r'mail@', r'contact@',
        r'example\.com', r'test\.com', r'placeholder', r'localhost',
        r'@facebook\.com', r'@twitter\.com', r'@instagram\.com',
        r'@linkedin\.com', r'@youtube\.com', r'@gmail\.com',
        r'@sentry\.', r'@sentry\.io', r'@sentry\.wixpress\.com',  # Sentry error tracking
        r'@wixpress\.com', r'@wix\.com',  # Wix platform emails
        r'@hubspot\.com', r'@mailchimp\.com', r'@constantcontact\.com',
        r'@sendgrid\.', r'@mailgun\.', r'@amazonaws\.com',
        r'[0-9a-f]{8}[0-9a-f]{4}[0-9a-f]{4}[0-9a-f]{4}[0-9a-f]{12}@',  # UUID-like patterns
        r'^[0-9a-f]{32}@',  # Hash-like patterns
    ]

    for email in emails:
        email_lower = email.lower()
        print(f"    🔍 Checking email: {email_lower}")

        excluded = False
        for pattern in exclude_patterns:
            if re.search(pattern, email_lower, re.IGNORECASE):
                print(f"    ❌ Excluded {email_lower} (matches pattern: {pattern})")
                excluded = True
                break

        if not excluded:
            print(f"    ✅ Accepted email: {email_lower}")
            filtered_emails.append(email_lower)

    print(f"    📧 Final filtered emails: {len(filtered_emails)}")
    print(f"    📧 Filtered emails list: {filtered_emails}")

    return list(set(filtered_emails))


async def extract_business_description(page):
    """Extract meaningful business description from various sources"""
    print("    📝 Starting business description extraction...")
    descriptions = []

    # Try different selectors for business descriptions
    selectors = [
        'meta[name="description"]',
        'meta[property="og:description"]',
        '[class*="about"]',
        '[class*="description"]',
        '[class*="intro"]',
        '[class*="mission"]',
        '[class*="vision"]',
        '[class*="services"]',
        'h1 + p',
        'h2 + p',
        '.hero p',
        '.banner p',
        'main p:first-of-type',
    ]

    for selector in selectors:
        try:
            print(f"    📝 Trying selector: {selector}")
            elements = await page.locator(selector).all()
            print(f"    📝 Found {len(elements)} elements for selector: {selector}")

            for element in elements:
                text = await element.text_content()
                if text and len(text.strip()) > 50:  # Only meaningful text
                    descriptions.append(text.strip())
                    print(f"    📝 Found description: {text.strip()[:100]}...")
        except Exception as e:
            print(f"    ⚠️ Error with selector {selector}: {e}")
            continue

    # If no specific descriptions found, get general page text
    if not descriptions:
        print("    📝 No specific descriptions found, trying general paragraphs...")
        try:
            paragraphs = await page.locator("p").all_text_contents()
            print(f"    📝 Found {len(paragraphs)} paragraphs")
            descriptions = [p.strip() for p in paragraphs if len(p.strip()) > 50]
            print(f"    📝 Filtered to {len(descriptions)} meaningful paragraphs")
        except Exception as e:
            print(f"    ⚠️ Error getting paragraphs: {e}")

    # Return best description (longest meaningful one)
    if descriptions:
        best_desc = max(descriptions, key=len)
        final_desc = best_desc[:500] if len(best_desc) > 500 else best_desc
        print(f"    📝 Selected best description: {final_desc[:100]}...")
        return final_desc

    print("    📝 No description found")
    return None


async def scrape_page_thoroughly(page, base_url):
    """Thoroughly scrape a page and related contact pages"""
    print(f"  🔍 Starting thorough scrape of: {base_url}")
    all_emails = set()
    description = None

    try:
        # First, extract from current page
        print("  📄 Extracting from main page...")
        content = await page.content()
        print(f"  📄 Page content length: {len(content)} characters")

        emails = await extract_emails_from_content(content)
        all_emails.update(emails)
        print(f"  📄 Main page emails: {emails}")

        # Get description from current page
        if not description:
            description = await extract_business_description(page)

        # Check for contact links and visit them
        contact_links = []

        # Look for contact page links
        print("  🔗 Building contact page URLs...")
        for contact_path in CONTACT_PAGES:
            try:
                contact_url = urljoin(base_url, contact_path)
                contact_links.append(contact_url)
                print(f"  🔗 Added contact URL: {contact_url}")
            except Exception as e:
                print(f"  ⚠️ Error building contact URL {contact_path}: {e}")
                continue

        # Also look for contact links in the page
        print("  🔗 Looking for contact links in page...")
        try:
            links = await page.locator('a[href*="contact"], a[href*="about"]').all()
            print(f"  🔗 Found {len(links)} contact/about links")

            for i, link in enumerate(links[:5]):  # Limit to avoid too many requests
                href = await link.get_attribute('href')
                if href:
                    full_url = urljoin(base_url, href)
                    contact_links.append(full_url)
                    print(f"  🔗 Added link {i + 1}: {full_url}")
        except Exception as e:
            print(f"  ⚠️ Error finding contact links: {e}")

        # Visit contact pages
        unique_contact_links = list(set(contact_links))[:3]  # Limit to 3 contact pages
        print(f"  🔗 Will visit {len(unique_contact_links)} contact pages")

        for i, contact_url in enumerate(unique_contact_links):
            try:
                print(f"  📧 [{i + 1}/{len(unique_contact_links)}] Checking contact page: {contact_url}")
                await page.goto(contact_url, timeout=15000)
                await page.wait_for_timeout(2000)

                contact_content = await page.content()
                print(f"  📧 Contact page content length: {len(contact_content)} characters")

                contact_emails = await extract_emails_from_content(contact_content)
                all_emails.update(contact_emails)
                print(f"  📧 Contact page emails: {contact_emails}")

                # Get description from contact page if not found yet
                if not description:
                    description = await extract_business_description(page)

            except Exception as e:
                print(f"  ⚠️ Could not access contact page {contact_url}: {e}")
                continue

        final_emails = list(all_emails)
        print(f"  ✅ Total emails found: {len(final_emails)}")
        print(f"  ✅ Final email list: {final_emails}")
        print(f"  ✅ Description found: {'Yes' if description else 'No'}")

        return final_emails, description

    except Exception as e:
        print(f"  ❌ Error during thorough scraping: {e}")
        return [], None


# Create async versions of Django ORM operations
@sync_to_async
def check_lead_exists(email, url):
    """Check if lead already exists"""
    return Lead.objects.filter(email=email, source_url=url).exists()


@sync_to_async
def create_lead(username, company_name, email,phone, niche, address, source_url, source_name, business_description):
    """Create new lead"""
    return Lead.objects.create(
        username=username,
        company_name=company_name,
        email=email,
        phone=phone,
        niche=niche,
        address=address,
        source_url=source_url,
        source_name=source_name,
        business_description=business_description
    )


async def process_csv_and_scrape(csv_path, niche):
    """Main function to process CSV and scrape websites"""
    print(f"🚀 Starting CSV processing and scraping...")
    print(f"📁 CSV file: {csv_path}")

    async with async_playwright() as p:
        print("🌐 Launching browser...")
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )

        processed_count = 0
        successful_extractions = 0

        try:
            print("📂 Opening CSV file...")
            with open(csv_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                print(f"📊 CSV columns: {reader.fieldnames}")

                for row in reader:
                    processed_count += 1
                    name = row.get('name', '').strip()
                    url = row.get('website', '').strip()
                    phone = row.get('phone', '').strip()
                    address = row.get('address', '').strip()
                    print(f"\n{'=' * 80}")
                    print(f"🔗 [{processed_count}] Processing: {name}")
                    print(f"🌐 URL: {url}")

                    if not url:
                        print(f"⚠️ No URL found for {name}")
                        continue

                    # Ensure URL has protocol
                    if not url.startswith(('http://', 'https://')):
                        url = 'https://' + url
                        print(f"🔧 Fixed URL: {url}")

                    try:
                        print(f"🚀 Creating new page...")
                        page = await context.new_page()

                        print(f"🌐 Navigating to: {url}")
                        await page.goto(url, timeout=30000, wait_until='domcontentloaded')
                        print(f"⏱️ Waiting for page to load...")
                        await page.wait_for_timeout(3000)

                        # Thorough scraping
                        print(f"🔍 Starting thorough scraping...")
                        emails, description = await scrape_page_thoroughly(page, url)

                        if emails:
                            print(f"✅ Found {len(emails)} email(s): {', '.join(emails)}")

                            for email in emails:
                                print(f"  💾 Processing email: {email}")

                                # Check if lead already exists (async)
                                exists = await check_lead_exists(email, url)
                                if not exists:
                                    print(f"  🆕 Creating new lead for: {email}")
                                    await create_lead(
                                        username=email.split('@')[0],
                                        company_name=name,
                                        email=email,
                                        niche=niche,
                                        source_url=url,
                                        phone=phone,
                                        address=address,
                                        source_name=name,
                                        business_description=description or f"Business contact from {name}"
                                    )
                                    print(f"  ✅ Saved lead: {email}")
                                else:
                                    print(f"  ⚠️ Lead already exists: {email}")

                            successful_extractions += 1
                        else:
                            print(f"❌ No emails found for {name}")

                        print(f"🗑️ Closing page...")
                        await page.close()

                        # Add delay between requests to be respectful
                        print(f"⏱️ Waiting 2 seconds before next request...")
                        await asyncio.sleep(2)

                    except Exception as e:
                        print(f"❌ Failed to scrape {url}: {e}")
                        print(f"❌ Error type: {type(e).__name__}")
                        continue

        except FileNotFoundError:
            print(f"❌ CSV file not found: {csv_path}")
        except Exception as e:
            print(f"❌ Error processing CSV: {e}")
        finally:
            print(f"🚫 Closing browser...")
            await browser.close()
            print(f"\n📊 FINAL SUMMARY:")
            print(f"📊 Processed: {processed_count} websites")
            print(f"📊 Successful extractions: {successful_extractions}")
            print(
                f"📊 Success rate: {(successful_extractions / processed_count) * 100:.1f}%" if processed_count > 0 else "0%")
            subject = "Genesis Google Map Extraction Completed "

            # Calculate success rate with 1 decimal place
            if processed_count > 0:
                success_rate = f"{(successful_extractions / processed_count) * 100:.1f}%"
            else:
                success_rate = "0%"

            message = f"""
Hi Michael,

Here's your scraping update from Genesis.ai:

- 📊 Processed: {processed_count} websites
- 📊 Successful extractions: {successful_extractions}
-   Success rate: {success_rate}
Keep grinding 💪

– Genesis.ai Bot
            """
            send_scraping_update(subject,message)

# Helper function to validate CSV structure
def validate_csv_structure(csv_path):
    """Validate that CSV has required columns"""
    print(f"🔍 Validating CSV structure: {csv_path}")
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

            print(f"📊 Found headers: {headers}")

            required_columns = ['name', 'website']
            missing_columns = [col for col in required_columns if col not in headers]

            if missing_columns:
                print(f"❌ Missing required columns: {missing_columns}")
                print(f"📊 Available columns: {headers}")
                return False

            # Count rows
            row_count = sum(1 for _ in reader)
            print(f"📊 CSV has {row_count} rows to process")
            print(f"✅ CSV structure validated successfully")
            return True

    except Exception as e:
        print(f"❌ Error validating CSV: {e}")
        return False


def run_email_extractor(csv_file: str, niche: str, validate=True, verbose=True):
    """
    Run the email extractor on a given CSV file.
    :param csv_file: Path to the CSV file.
    :param validate: Whether to validate the CSV structure.
    :param verbose: Whether to print logs.
    :return: List of scraped leads or empty list if validation fails.
    """
    if verbose:
        print("🎯 EMAIL SCRAPER STARTING")
        print("=" * 80)

    if not validate or validate_csv_structure(csv_file):
        if verbose:
            print("\n🚀 Starting scraping process...")
        return asyncio.run(process_csv_and_scrape(csv_file, niche))
    else:
        if verbose:
            print("❌ Please fix CSV structure before running.")
        return []

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run email extractor on a CSV file.")
    parser.add_argument("niche", help="Niche label to associate with scraped leads.")

    args = parser.parse_args()

    csv_file = "csv-json/home_staging_in_Utah.csv"
    run_email_extractor(csv_file, niche=args.niche)


