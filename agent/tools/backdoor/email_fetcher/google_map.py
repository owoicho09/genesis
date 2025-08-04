import csv
import json
import time
import os
from urllib.parse import quote, urlparse, unquote
from playwright.sync_api import sync_playwright
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

import django
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")  # <- replace with your project

django.setup()
from agent.tools.utils.send_email_update import send_scraping_update

class MapsBusinessScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self.results = []
        self.seen_names = set()
        self.visited_urls = set()
        self.skipped_cards = []  # Track skipped cards
        self.visited_urls_file = "csv-json/google_map_urls.json"
        self.pagination_state_file = "csv-json/pagination_state.json"
        self.pagination_state = {}
        self.all_discovered_urls = set()  # Track all URLs discovered during scraping
        self.load_visited_urls()
        self.load_pagination_state()

    def load_existing_businesses(self, csv_file):
        """Load existing business names from CSV file to avoid re-scraping"""
        try:
            if os.path.exists(csv_file):
                with open(csv_file, mode="r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.seen_names.add(row['name'].strip().lower())
                print(f"📂 Loaded {len(self.seen_names)} existing business names from {csv_file}")
            else:
                print(f"📂 No existing CSV file found ({csv_file}), starting fresh")
        except Exception as e:
            print(f"⚠️ Error loading existing businesses: {e}")

    def load_visited_urls(self):
        """Load previously visited URLs from file"""
        try:
            if os.path.exists(self.visited_urls_file):
                with open(self.visited_urls_file, 'r') as f:
                    self.visited_urls = set(json.load(f))
                print(f"📂 Loaded {len(self.visited_urls)} previously visited URLs")
            else:
                self.visited_urls = set()
                print("📂 No previous URL history found, starting fresh")
        except Exception as e:
            print(f"⚠️ Error loading visited URLs: {e}")
            self.visited_urls = set()

    def load_pagination_state(self):
        """Load pagination state to continue from where we left off"""
        try:
            if os.path.exists(self.pagination_state_file):
                with open(self.pagination_state_file, 'r') as f:
                    self.pagination_state = json.load(f)
                print(f"📂 Loaded pagination state for {len(self.pagination_state)} queries")
            else:
                self.pagination_state = {}
                print("📂 No pagination state found, starting fresh")
        except Exception as e:
            print(f"⚠️ Error loading pagination state: {e}")
            self.pagination_state = {}

    def save_pagination_state(self):
        """Save pagination state to continue later"""
        try:
            os.makedirs(os.path.dirname(self.pagination_state_file), exist_ok=True)
            with open(self.pagination_state_file, 'w') as f:
                json.dump(self.pagination_state, f, indent=2)
            print(f"💾 Saved pagination state to {self.pagination_state_file}")
        except Exception as e:
            print(f"⚠️ Error saving pagination state: {e}")

    def save_visited_urls(self):
        """Save visited URLs to file with duplicate prevention"""
        try:
            os.makedirs(os.path.dirname(self.visited_urls_file), exist_ok=True)

            # Load existing URLs from file
            existing_urls = set()
            if os.path.exists(self.visited_urls_file):
                try:
                    with open(self.visited_urls_file, 'r') as f:
                        existing_urls = set(json.load(f))
                except:
                    existing_urls = set()

            # Merge with current visited URLs (set automatically handles duplicates)
            merged_urls = existing_urls.union(self.visited_urls)

            # Save the merged set
            with open(self.visited_urls_file, 'w') as f:
                json.dump(sorted(list(merged_urls)), f, indent=2)

            new_urls_count = len(merged_urls) - len(existing_urls)
            print(f"💾 Saved {len(merged_urls)} visited URLs to {self.visited_urls_file}")
            print(f"   📊 {new_urls_count} new URLs added, {len(existing_urls)} existing URLs preserved")

            # Update the instance variable with the merged set
            self.visited_urls = merged_urls
        except Exception as e:
            print(f"⚠️ Error saving visited URLs: {e}")

    def extract_website_from_redirect(self, redirect_url):
        """Extract actual website URL from Google's redirect URL"""
        try:
            if not redirect_url or redirect_url.startswith(':///aclk'):
                return ""

            # Handle different types of redirect URLs
            if 'url=' in redirect_url:
                # Extract from url parameter
                parts = redirect_url.split('url=')
                if len(parts) > 1:
                    url_part = parts[1].split('&')[0]
                    return unquote(url_part)

            if redirect_url.startswith('https://www.google.com/url?'):
                # Extract from Google redirect
                if 'q=' in redirect_url:
                    parts = redirect_url.split('q=')
                    if len(parts) > 1:
                        url_part = parts[1].split('&')[0]
                        return unquote(url_part)

            return redirect_url
        except:
            return ""

    def clean_url(self, url):
        """Clean and normalize URL"""
        if not url:
            return ""

        # Remove tracking parameters and fragments
        try:
            parsed = urlparse(url)
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            return clean_url.rstrip('/')
        except:
            return url

    def is_valid_website(self, url):
        """Check if URL is a valid business website"""
        if not url:
            return False

        # Skip Google, social media, and other non-business sites
        skip_domains = [
            'google.com', 'maps.google.com', 'facebook.com', 'instagram.com',
            'twitter.com', 'linkedin.com', 'youtube.com', 'tiktok.com',
            'yelp.com', 'tripadvisor.com', 'foursquare.com', 'pinterest.com',
            'amazon.com', 'ebay.com', 'craigslist.org', 'wikipedia.org',
            'apple.com', 'microsoft.com', 'android.com', 'ios.com'
        ]

        url_lower = url.lower()
        return not any(domain in url_lower for domain in skip_domains)



    def extract_phone_from_text(self, text):
        """Extract phone number from text using regex patterns"""
        if not text:
            return ""

        # Phone number patterns
        phone_patterns = [
            # International format: +1 (555) 123-4567
            r'\+\d{1,3}\s*\(\d{3}\)\s*\d{3}[-.\s]*\d{4}',
            # International format: +1 555-123-4567
            r'\+\d{1,3}\s*\d{3}[-.\s]*\d{3}[-.\s]*\d{4}',
            # US format: (555) 123-4567
            r'\(\d{3}\)\s*\d{3}[-.\s]*\d{4}',
            # US format: 555-123-4567
            r'\d{3}[-.\s]*\d{3}[-.\s]*\d{4}',
            # International with country code: +1234567890
            r'\+\d{10,15}',
            # Simple 10-digit: 5551234567
            r'\b\d{10}\b',
            # With spaces: 555 123 4567
            r'\d{3}\s+\d{3}\s+\d{4}'
        ]

        for pattern in phone_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                cleaned = self.clean_phone(match)
                if self.is_valid_phone(cleaned):
                    return cleaned

        return ""


    def is_valid_phone(self, phone):
        """Check if the extracted phone number is valid"""
        if not phone:
            return False

        # Remove all non-digit characters for validation
        digits_only = re.sub(r'\D', '', phone)

        # Check if it has reasonable length (7-15 digits)
        if len(digits_only) < 7 or len(digits_only) > 15:
            return False

        # Check if it's not all the same digit (like 1111111111)
        if len(set(digits_only)) == 1:
            return False

        # Check if it's not a common fake number
        fake_patterns = ['1234567890', '0000000000', '9999999999']
        if digits_only in fake_patterns:
            return False

        return True


    def clean_phone(self, phone):
        """Clean and format phone number"""
        if not phone:
            return ""

        # Remove extra whitespace
        phone = phone.strip()

        # Remove common prefixes like "tel:"
        if phone.startswith('tel:'):
            phone = phone[4:]

        # Basic formatting - keep the original format but clean it up
        phone = re.sub(r'\s+', ' ', phone)  # Replace multiple spaces with single space

        return phone


    def extract_address_from_text(self, text):
        """Extract address from text using patterns"""
        if not text or len(text.strip()) < 5:
            return ""

        text = text.strip()

        # Skip obviously non-address text
        skip_patterns = [
            'call', 'website', 'menu', 'photos', 'reviews', 'hours',
            'directions to', 'get directions', 'save', 'share', 'nearby'
        ]

        if any(pattern in text.lower() for pattern in skip_patterns):
            return ""

        # Common address patterns
        address_patterns = [
            # Full address with street number, street name, city, state, zip
            r'\b\d+\s+[A-Za-z0-9\s,.-]+(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|way|place|pl|court|ct|circle|cir)\s*,?\s*[A-Za-z\s]+,?\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?\b',

            # Address with street and city/state
            r'\b\d+\s+[A-Za-z0-9\s,.-]+(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|way|place|pl|court|ct|circle|cir)\s*,\s*[A-Za-z\s]+,?\s*[A-Z]{2}\b',

            # Simple street address
            r'\b\d+\s+[A-Za-z0-9\s,.-]+(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|way|place|pl|court|ct|circle|cir)\b',

            # International address patterns
            r'\b\d+\s+[A-Za-z0-9\s,.-]+,\s*[A-Za-z\s]+\s+\d{4,6}\b',  # International format
        ]

        for pattern in address_patterns:
            import re
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Return the longest match (likely most complete address)
                longest_match = max(matches, key=len)
                return longest_match.strip()

        # If no pattern matches, check if the text looks like an address
        # (contains numbers and common address words)
        if (re.search(r'\d+', text) and
                any(word in text.lower() for word in ['street', 'st', 'avenue', 'ave', 'road', 'rd', 'drive', 'dr']) and
                len(text) > 10 and len(text) < 200):
            return text.strip()

        return ""

    def extract_address_from_structured_data(self, data):
        """Extract address from structured data (JSON-LD)"""
        try:
            # Handle different structured data formats
            if isinstance(data, list):
                for item in data:
                    address = self.extract_address_from_structured_data(item)
                    if address:
                        return address

            elif isinstance(data, dict):
                # Look for address in common structured data fields
                address_fields = ['address', 'streetAddress', 'location', 'geo']

                for field in address_fields:
                    if field in data:
                        address_data = data[field]

                        if isinstance(address_data, str):
                            return address_data.strip()

                        elif isinstance(address_data, dict):
                            # Build address from components
                            address_parts = []

                            # Common address components
                            components = ['streetAddress', 'addressLocality', 'addressRegion', 'postalCode']
                            for component in components:
                                if component in address_data and address_data[component]:
                                    address_parts.append(str(address_data[component]).strip())

                            if address_parts:
                                return ', '.join(address_parts)

                # Recursively search in nested objects
                for key, value in data.items():
                    if isinstance(value, (dict, list)):
                        address = self.extract_address_from_structured_data(value)
                        if address:
                            return address

        except Exception as e:
            print(f"⚠️ Error extracting from structured data: {e}")

        return ""



    def extract_rating_from_text(self, text):
        # Extract float rating from "4.7 stars" or similar
        match = re.search(r"([0-5]\.\d)", text)
        return float(match.group(1)) if match else None

    def extract_review_count_from_text(self, text):
        # Extract number from "123 reviews"
        match = re.search(r"([\d,]+)", text)
        if match:
            return int(match.group(1).replace(",", ""))
        return None


    def extract_business_info(self, page):
        """Extract business name and website from the current page"""
        business_info = {"name": "", "website": "", "phone": ""}

        try:
            print("🔍 Extracting business name...")

            # Try multiple selectors for business name
            name_selectors = [
                'h1.DUwDvf',
                'h1[data-attrid="title"]',
                'h1.x3AX1-LfntMc-header-title-title',
                'h1',
                '[data-attrid="title"]',
                '.x3AX1-LfntMc-header-title-title',
                '.DUwDvf',
                '.qrShPb',
                '.SPZz6b h1'
            ]

            name = ""
            for selector in name_selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0:
                        name = element.inner_text().strip()
                        if name:
                            print(f"✅ Found business name with selector '{selector}': {name}")
                            break
                except:
                    continue

            if not name:
                print("⚠️ Could not find business name, using placeholder")
                name = "Unknown Business"

            business_info["name"] = name

            print("🔍 Extracting website...")

            # IMPROVED WEBSITE EXTRACTION
            website = ""

            # Method 1: Look for website in business info panel
            website_selectors = [
                # New selectors for current Google Maps
                'a[data-item-id="authority"]',
                'a[data-item-id*="website"]',
                'a[jsaction*="website"]',
                'a[aria-label*="Website"]',
                'a[data-value="Website"]',
                'a[href*="http"]:has-text("Website")',
                '.AeaXub a[href*="http"]',  # Business info section
                '.RcCsl a[href*="http"]',  # Contact section
                '.CsEnBe a[href*="http"]',  # Action buttons
                '.lcr4fd a[href*="http"]'  # Business details
            ]

            for selector in website_selectors:
                try:
                    elements = page.locator(selector)
                    for i in range(min(elements.count(), 3)):  # Check first 3 matches
                        element = elements.nth(i)
                        href = element.get_attribute('href')

                        if href:
                            # Handle redirect URLs
                            if href.startswith(':///aclk') or 'google.com/url?' in href:
                                print(f"🔄 Found redirect URL, trying to extract real URL: {href[:50]}...")

                                # Method A: Click and get redirected URL
                                try:
                                    # Open in new tab to avoid losing current page
                                    with page.context.new_page() as new_page:
                                        new_page.goto(href, timeout=10000)
                                        new_page.wait_for_load_state('networkidle', timeout=5000)
                                        actual_url = new_page.url

                                        if actual_url and actual_url != href and self.is_valid_website(actual_url):
                                            website = self.clean_url(actual_url)
                                            print(f"✅ Extracted website via redirect: {website}")
                                            break
                                except Exception as e:
                                    print(f"⚠️ Could not follow redirect: {e}")
                                    continue

                                # Method B: Extract from URL parameters
                                extracted_url = self.extract_website_from_redirect(href)
                                if extracted_url and self.is_valid_website(extracted_url):
                                    website = self.clean_url(extracted_url)
                                    print(f"✅ Extracted website from redirect parameters: {website}")
                                    break

                            elif self.is_valid_website(href):
                                website = self.clean_url(href)
                                print(f"✅ Found direct website: {website}")
                                break

                    if website:
                        break

                except Exception as e:
                    print(f"⚠️ Error with selector '{selector}': {e}")
                    continue

            # Method 2: Look for website in page source if not found
            if not website:
                print("🔍 Searching page source for website patterns...")
                try:
                    page_content = page.content()

                    # Look for common website patterns
                    url_patterns = [
                        r'https?://(?:www\.)?([a-zA-Z0-9-]+\.(?:com|org|net|edu|gov|co|io|biz|info))',
                        r'"(https?://[^"]*\.(com|org|net|edu|gov|co|io|biz|info)[^"]*)"',
                        r'url=(https?://[^&]*)'
                    ]

                    for pattern in url_patterns:
                        matches = re.findall(pattern, page_content, re.IGNORECASE)
                        for match in matches:
                            potential_url = match[0] if isinstance(match, tuple) else match
                            if potential_url.startswith('http') and self.is_valid_website(potential_url):
                                website = self.clean_url(potential_url)
                                print(f"✅ Found website in page source: {website}")
                                break
                        if website:
                            break

                except Exception as e:
                    print(f"⚠️ Error searching page source: {e}")

            # Method 3: Look through all visible links as last resort
            if not website:
                print("🔍 Searching through all visible links...")
                try:
                    links = page.locator('a[href*="http"]')
                    link_count = min(links.count(), 50)  # Limit to avoid too much processing

                    for i in range(link_count):
                        try:
                            href = links.nth(i).get_attribute('href')
                            if href and self.is_valid_website(href):
                                # Skip obvious non-business links
                                if any(skip in href.lower() for skip in
                                       ['maps.google', 'facebook.com', 'instagram.com']):
                                    continue

                                website = self.clean_url(href)
                                print(f"✅ Found website in general links: {website}")
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"⚠️ Error searching links: {e}")

            if not website:
                print("⚠️ No website found for this business")

            business_info["website"] = website

            # PHONE NUMBER EXTRACTION
            print("🔍 Extracting phone number...")

            phone = ""

            # Method 1: Look for phone number in business info panel
            phone_selectors = [
                # Common phone number selectors in Google Maps
                'button[data-item-id="phone:tel:"]',
                'button[aria-label*="Call"]',
                'a[href^="tel:"]',
                'button[jsaction*="phone"]',
                '[data-item-id*="phone"]',
                'button:has-text("Call")',
                '.rogA2c button',  # Phone button area
                '.AeaXub button[data-item-id*="phone"]',  # Business info section
                '.RcCsl button[aria-label*="Call"]',  # Contact section
                '.CsEnBe a[href^="tel:"]',  # Action buttons
                '.lcr4fd button[data-item-id*="phone"]',  # Business details
                'span:has-text("+")',  # Look for phone numbers with country codes
                'span[jsaction*="phone"]'
            ]

            for selector in phone_selectors:
                try:
                    elements = page.locator(selector)
                    for i in range(min(elements.count(), 3)):
                        element = elements.nth(i)

                        # Try to get phone from href attribute
                        href = element.get_attribute('href')
                        if href and href.startswith('tel:'):
                            phone = href.replace('tel:', '').strip()
                            if self.is_valid_phone(phone):
                                phone = self.clean_phone(phone)
                                print(f"✅ Found phone from tel: link: {phone}")
                                break

                        # Try to get phone from aria-label
                        aria_label = element.get_attribute('aria-label')
                        if aria_label and ('call' in aria_label.lower() or 'phone' in aria_label.lower()):
                            extracted_phone = self.extract_phone_from_text(aria_label)
                            if extracted_phone:
                                phone = extracted_phone
                                print(f"✅ Found phone from aria-label: {phone}")
                                break

                        # Try to get phone from data attributes
                        data_item_id = element.get_attribute('data-item-id')
                        if data_item_id and 'phone' in data_item_id:
                            # Extract phone from data-item-id like "phone:tel:+1234567890"
                            if ':tel:' in data_item_id:
                                phone_part = data_item_id.split(':tel:')[-1]
                                if self.is_valid_phone(phone_part):
                                    phone = self.clean_phone(phone_part)
                                    print(f"✅ Found phone from data-item-id: {phone}")
                                    break

                        # Try to get phone from text content
                        text_content = element.inner_text()
                        if text_content:
                            extracted_phone = self.extract_phone_from_text(text_content)
                            if extracted_phone:
                                phone = extracted_phone
                                print(f"✅ Found phone from text content: {phone}")
                                break

                    if phone:
                        break

                except Exception as e:
                    print(f"⚠️ Error with phone selector '{selector}': {e}")
                    continue

            # Method 2: Search page content for phone patterns
            if not phone:
                print("🔍 Searching page content for phone patterns...")
                try:
                    page_content = page.content()
                    phone = self.extract_phone_from_text(page_content)
                    if phone:
                        print(f"✅ Found phone in page content: {phone}")
                except Exception as e:
                    print(f"⚠️ Error searching page content for phone: {e}")

            # Method 3: Look through all text elements for phone numbers
            if not phone:
                print("🔍 Searching all text elements for phone numbers...")
                try:
                    # Look for any element containing phone-like patterns
                    text_elements = page.locator('span, div, p, a').all()
                    for element in text_elements[:100]:  # Limit to avoid too much processing
                        try:
                            text = element.inner_text()
                            if text:
                                extracted_phone = self.extract_phone_from_text(text)
                                if extracted_phone:
                                    phone = extracted_phone
                                    print(f"✅ Found phone in text element: {phone}")
                                    break
                        except:
                            continue
                except Exception as e:
                    print(f"⚠️ Error searching text elements: {e}")

            if not phone:
                print("⚠️ No phone number found for this business")

            business_info["phone"] = phone


            # ADDRESS EXTRACTION
            print("🔍 Extracting address...")

            address = ""

            # Method 1: Look for address in specific Google Maps selectors
            address_selectors = [
                # Primary address selectors
                'button[data-item-id="address"]',
                'button[data-value="Address"]',
                'button[aria-label*="Address"]',
                '[data-item-id="address"]',
                'button[jsaction*="address"]',

                # Business info panel selectors
                '.AeaXub button[data-item-id="address"]',
                '.RcCsl button[data-value="Address"]',
                '.CsEnBe [data-item-id="address"]',
                '.lcr4fd button[data-item-id="address"]',

                # Address-related buttons and links
                'button:has-text("Directions")',
                'a[href*="directions"]',
                'button[aria-label*="Get directions"]',

                # General address containers
                '.Io6YTe',  # Address area
                '.LrzXr',   # Business details
                '.rogA2c',  # Info panel
                '.AeaXub .fontBodyMedium',  # Business info text

                # Text elements that might contain addresses
                'span[jstcache*="address"]',
                'div[jsaction*="address"]'
            ]

            for selector in address_selectors:
                try:
                    elements = page.locator(selector)
                    for i in range(min(elements.count(), 3)):
                        element = elements.nth(i)

                        # Try to get address from aria-label
                        aria_label = element.get_attribute('aria-label')
                        if aria_label:
                            # Look for address patterns in aria-label
                            extracted_address = self.extract_address_from_text(aria_label)
                            if extracted_address:
                                address = extracted_address
                                print(f"✅ Found address from aria-label: {address}")
                                break

                        # Try to get address from text content
                        text_content = element.inner_text().strip()
                        if text_content:
                            extracted_address = self.extract_address_from_text(text_content)
                            if extracted_address:
                                address = extracted_address
                                print(f"✅ Found address from text content: {address}")
                                break

                        # Try to get address from data attributes
                        data_item_id = element.get_attribute('data-item-id')
                        if data_item_id and 'address' in data_item_id:
                            # Sometimes address is in the data attribute value
                            data_value = element.get_attribute('data-value')
                            if data_value:
                                extracted_address = self.extract_address_from_text(data_value)
                                if extracted_address:
                                    address = extracted_address
                                    print(f"✅ Found address from data-value: {address}")
                                    break

                    if address:
                        break

                except Exception as e:
                    print(f"⚠️ Error with address selector '{selector}': {e}")
                    continue

            # Method 2: Look for address in the URL or page data
            if not address:
                print("🔍 Searching URL and page data for address...")
                try:
                    current_url = page.url

                    # Extract coordinates or place data from URL
                    import urllib.parse
                    parsed_url = urllib.parse.urlparse(current_url)

                    # Check if there's place data in the URL
                    if 'place/' in current_url:
                        place_part = current_url.split('place/')[-1].split('/')[0]
                        decoded_place = urllib.parse.unquote(place_part)
                        # Often contains address information
                        extracted_address = self.extract_address_from_text(decoded_place)
                        if extracted_address:
                            address = extracted_address
                            print(f"✅ Found address from URL place data: {address}")

                except Exception as e:
                    print(f"⚠️ Error extracting from URL: {e}")

            # Method 3: Search page content for address patterns
            if not address:
                print("🔍 Searching page content for address patterns...")
                try:
                    page_content = page.content()
                    address = self.extract_address_from_text(page_content)
                    if address:
                        print(f"✅ Found address in page content: {address}")
                except Exception as e:
                    print(f"⚠️ Error searching page content for address: {e}")

            # Method 4: Look through all text elements for addresses
            if not address:
                print("🔍 Searching all text elements for address patterns...")
                try:
                    # Look for elements that might contain address information
                    text_selectors = [
                        'span', 'div', 'p', 'button', 'a',
                        '.fontBodyMedium', '.fontBodySmall',
                        '[role="button"]', '[jsaction]'
                    ]

                    for selector in text_selectors:
                        elements = page.locator(selector)
                        element_count = min(elements.count(), 100)  # Limit processing

                        for i in range(element_count):
                            try:
                                element = elements.nth(i)
                                text = element.inner_text().strip()
                                if text and len(text) > 10:  # Skip very short text
                                    extracted_address = self.extract_address_from_text(text)
                                    if extracted_address:
                                        address = extracted_address
                                        print(f"✅ Found address in text element: {address}")
                                        break
                            except:
                                continue

                        if address:
                            break

                except Exception as e:
                    print(f"⚠️ Error searching text elements for address: {e}")

            # Method 5: Try to get address from structured data
            if not address:
                print("🔍 Searching for structured data...")
                try:
                    # Look for JSON-LD or other structured data
                    scripts = page.locator('script[type="application/ld+json"]')
                    for i in range(min(scripts.count(), 5)):
                        try:
                            script_content = scripts.nth(i).inner_text()
                            import json
                            data = json.loads(script_content)

                            # Look for address in structured data
                            if isinstance(data, dict):
                                address_data = self.extract_address_from_structured_data(data)
                                if address_data:
                                    address = address_data
                                    print(f"✅ Found address in structured data: {address}")
                                    break
                        except:
                            continue
                except Exception as e:
                    print(f"⚠️ Error searching structured data: {e}")

            if not address:
                print("⚠️ No address found for this business")

            business_info["address"] = address



            # ⭐ RATING AND REVIEW COUNT EXTRACTION
            print("🔍 Extracting rating and review count...")

            rating = ""
            review_count = ""

            try:
                # Rating selector (stars)
                rating_element = page.locator('span[aria-label*="stars"], .MW4etd').first
                if rating_element.count() > 0:
                    rating_text = rating_element.inner_text().strip()
                    rating = self.extract_rating_from_text(rating_text)
                    print(f"✅ Found rating: {rating}")

                # Review count selector
                review_count_element = page.locator('span:has-text("review"), span:has-text("reviews")').first
                if review_count_element.count() > 0:
                    review_text = review_count_element.inner_text().strip()
                    review_count = self.extract_review_count_from_text(review_text)
                    print(f"✅ Found review count: {review_count}")

            except Exception as e:
                print(f"⚠️ Error extracting rating/reviews: {e}")

            business_info["rating"] = rating
            business_info["review_count"] = review_count



        except Exception as e:
            print(f"⚠️ Error extracting business info: {e}")

        return business_info

    def verify_detail_page_loaded(self, page, business_name=""):
        """Verify that the business detail page has actually loaded"""
        try:
            # Check for business detail indicators
            detail_indicators = [
                'h1.DUwDvf',  # Business name
                '[data-attrid="title"]',  # Title attribute
                '.qrShPb',  # Alternative business name
                '.SPZz6b h1',  # Another business name variant
                'button[jsaction*="directions"]',  # Directions button
                'button[aria-label*="Call"]',  # Call button
            ]

            for indicator in detail_indicators:
                if page.locator(indicator).count() > 0:
                    print(f"✅ Detail page loaded - found indicator: {indicator}")
                    return True

            print("❌ Detail page not loaded - no indicators found")
            return False

        except Exception as e:
            print(f"⚠️ Error verifying detail page: {e}")
            return False

    def safe_click_card(self, card, card_index):
        """Safely click a card with multiple attempts and verification"""
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                print(f"🖱️ Attempt {attempt + 1}/{max_attempts} - Clicking card {card_index}")

                # Scroll card into view
                print("📍 Scrolling card into view...")
                card.scroll_into_view_if_needed()
                time.sleep(1)

                # Ensure card is clickable
                card.wait_for(state='visible', timeout=5000)

                # Get card URL for verification
                card_url = card.get_attribute('href')
                print(f"🔗 Card URL: {card_url}")

                # Click the card
                card.click()

                # Wait for page to load
                time.sleep(3)

                # Verify the detail page loaded
                if self.verify_detail_page_loaded(card.page):
                    print(f"✅ Card {card_index} clicked successfully!")
                    return True, card_url
                else:
                    print(f"❌ Card {card_index} click failed - detail page not loaded")
                    if attempt < max_attempts - 1:
                        print("🔄 Retrying click...")
                        time.sleep(2)
                    continue

            except Exception as e:
                print(f"❌ Error clicking card {card_index} (attempt {attempt + 1}): {e}")
                if attempt < max_attempts - 1:
                    print("🔄 Retrying click...")
                    time.sleep(2)
                continue

        print(f"❌ Failed to click card {card_index} after {max_attempts} attempts")
        return False, None

    def discover_all_cards(self, page):
        """Discover all cards by scrolling through the entire feed"""
        print("\n🔍 DISCOVERING ALL CARDS ON PAGE...")
        print("=" * 50)

        discovered_cards = set()
        scrollable = page.locator('div[role="feed"]')

        if scrollable.count() == 0:
            print("❌ Could not find scrollable feed")
            return []

        # Go to top first
        scrollable.evaluate("el => el.scrollTo(0, 0)")
        time.sleep(2)

        scroll_attempts = 0
        max_scroll_attempts = 20
        no_new_cards_count = 0

        while scroll_attempts < max_scroll_attempts and no_new_cards_count < 3:
            # Get current cards
            cards = page.locator('a[href*="/maps/place/"]')
            current_cards = set()

            for i in range(cards.count()):
                try:
                    card_url = cards.nth(i).get_attribute('href')
                    if card_url:
                        current_cards.add(card_url)
                        self.all_discovered_urls.add(card_url)
                except:
                    continue

            # Check if we found new cards
            new_cards = current_cards - discovered_cards
            if new_cards:
                print(f"✅ Found {len(new_cards)} new cards (total: {len(current_cards)})")
                discovered_cards.update(new_cards)
                no_new_cards_count = 0
            else:
                no_new_cards_count += 1
                print(f"⚠️ No new cards found (attempt {no_new_cards_count}/3)")

            # Scroll down
            scrollable.evaluate("el => el.scrollBy(0, 1000)")
            time.sleep(2)
            scroll_attempts += 1

            # Check if we've reached the end
            if no_new_cards_count >= 3:
                print("🛑 No more new cards found after multiple attempts")
                break

        print(f"📊 DISCOVERY COMPLETE: Found {len(discovered_cards)} total cards")
        return list(discovered_cards)

    def get_unvisited_cards_from_discovered(self, discovered_urls):
        """Get unvisited cards from discovered URLs"""
        unvisited_urls = []

        for url in discovered_urls:
            if url not in self.visited_urls:
                unvisited_urls.append(url)

        print(f"📊 UNVISITED CARDS: {len(unvisited_urls)} out of {len(discovered_urls)} total discovered")
        return unvisited_urls

    def navigate_to_card_directly(self, page, card_url):
        """Navigate directly to a card URL"""
        try:
            print(f"🎯 Navigating directly to: {card_url}")
            page.goto(card_url, timeout=30000)
            time.sleep(3)

            if self.verify_detail_page_loaded(page):
                print("✅ Successfully navigated to card detail page")
                return True
            else:
                print("❌ Failed to load detail page")
                return False

        except Exception as e:
            print(f"❌ Error navigating to card: {e}")
            return False

    def perform_clean_sweep(self, page, output_csv, max_results):
        """Perform a clean sweep of all unvisited URLs"""
        print(f"\n🧹 PERFORMING CLEAN SWEEP OF UNVISITED URLS")
        print("=" * 60)

        discovered_urls = self.discover_all_cards(page)

        if not discovered_urls:
            print("❌ No cards discovered")
            return 0

        unvisited_urls = self.get_unvisited_cards_from_discovered(discovered_urls)

        if not unvisited_urls:
            print("✅ All discovered cards have been visited!")
            return 0

        processed_count = 0
        print(f"\n🎯 PROCESSING {len(unvisited_urls)} UNVISITED CARDS...")

        for i, card_url in enumerate(unvisited_urls):
            if processed_count >= max_results:
                print(f"🛑 Reached maximum results limit ({max_results})")
                break

            print(f"\n{'=' * 50}")
            print(f"🔄 Processing card {i + 1}/{len(unvisited_urls)}")
            print(f"🔗 URL: {card_url}")
            print(f"📊 Progress: {processed_count}/{max_results}")

            try:
                if self.navigate_to_card_directly(page, card_url):
                    self.visited_urls.add(card_url)
                    business_info = self.extract_business_info(page)

                    business_name = business_info.get("name", "").strip()
                    if not business_name or business_name.lower() == "unknown business":
                        print("⚠️ Could not extract valid business name")
                        continue

                    business_name_lower = business_name.lower()
                    if business_name_lower in self.seen_names:
                        print(f"⚠️ Skipping duplicate business: {business_info['name']}")
                        continue

                    # Grab rating and review count safely
                    raw_rating = business_info.get("rating")
                    raw_review_count = business_info.get("review_count")

                    if raw_review_count is None:
                        print(f"❌ Skipped: Missing rating or review count")
                        continue

                    try:
                        #rating = float(raw_rating)
                        review_count = int(raw_review_count)
                    except (ValueError, TypeError):
                        print(f"❌ Skipped: Rating/Review count not a valid number")
                        continue

                    # Filters
                    if review_count < 10 or review_count > 50:
                        print(f"⚠️ Skipped {business_info['name']} ({review_count} reviews outside target range)")
                        continue

                    #if rating > 3.8:
                    #    print(f"⚠️ Skipped {business_info['name']} (rating too high)")
                    #    continue

                    self.seen_names.add(business_name_lower)
                    self.results.append(business_info)
                    processed_count += 1

                    print(f"✅ SUCCESS! Business {processed_count} saved:")
                    print(f"   📍 Name: {business_info['name']}")
                    print(f"   🌐 Website: {business_info['website'] or 'Not found'}")
                    print(f"   📞 Phone: {business_info['phone'] or 'Not found'}")
                    print(f"   📌 Address: {business_info['address'] or 'No address found'}")
                    print(f"   ⭐ Rating: Nil for now | 🗣 Reviews: {review_count}")

                    if processed_count % 3 == 0:
                        self.save_to_csv(output_csv)
                        self.save_visited_urls()
                        print(f"💾 Intermediate save completed")
                else:
                    print("❌ Failed to navigate to card")

            except Exception as e:
                print(f"❌ Error processing card: {e}")

        print(f"\n✅ CLEAN SWEEP COMPLETED: {processed_count} businesses saved")
        return processed_count

    def scrape(self, query, max_results=15, output_csv=None, continue_from_last=True, clean_sweep=True):
        """
        Scrape Google Maps businesses with optional clean sweep of unvisited URLs

        Args:
            query: Search query
            max_results: Maximum number of results to collect
            output_csv: Output CSV file path (auto-generated if None)
            continue_from_last: Whether to continue from last pagination state
            clean_sweep: Whether to perform clean sweep of unvisited URLs
        """
        if output_csv is None:
            output_csv = f"csv-json/{query.replace(' ', '_')}.csv"

        # Load existing businesses to avoid duplicates
        self.load_existing_businesses(output_csv)

        search_url = f"https://www.google.com/maps/search/{quote(query)}"

        print(f"\n🚀 STARTING GOOGLE MAPS SCRAPER")
        print(f"=" * 50)
        print(f"🔍 Query: {query}")
        print(f"📊 Max results: {max_results}")
        print(f"📁 Output file: {output_csv}")
        print(f"🧹 Clean sweep: {clean_sweep}")
        print(f"🌐 Search URL: {search_url}")
        print(f"=" * 50)

        with sync_playwright() as p:
            print("🌐 Launching browser...")
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = context.new_page()

            try:
                print("🔍 Navigating to Google Maps...")
                page.goto(search_url, timeout=60000)
                print("✅ Page loaded successfully")

                print("⏱️ Waiting for page to stabilize...")
                page.wait_for_timeout(5000)

                # Handle cookie consent if it appears
                try:
                    cookie_button = page.locator(
                        'button:has-text("Accept all"), button:has-text("I agree"), button:has-text("Accept")')
                    if cookie_button.count() > 0:
                        print("🍪 Accepting cookies...")
                        cookie_button.first.click()
                        page.wait_for_timeout(2000)
                except:
                    pass

                # Perform clean sweep if requested
                if clean_sweep:
                    processed_count = self.perform_clean_sweep(page, output_csv, max_results)
                    print(f"\n✅ Clean sweep completed! Processed {processed_count} businesses")
                else:
                    print("⚠️ Clean sweep disabled, using original card-by-card method")
                    # Original scraping logic would go here
                    processed_count = 0

            except Exception as e:
                print(f"❌ Critical error during scraping: {e}")
            finally:
                print("🔒 Closing browser...")
                browser.close()

        # Save final results
        self.save_to_csv(output_csv)
        self.save_visited_urls()

        print(f"\n🎉 FINAL RESULTS:")
        print(f"📁 {len(self.results)} businesses saved to {output_csv}")
        print(f"🌐 {len(self.visited_urls)} URLs tracked")
        print(f"🔍 {len(self.all_discovered_urls)} total URLs discovered")
        print(f"⏭️ {len(self.skipped_cards)} cards skipped")

    def save_to_csv(self, filename):
        """Save results to CSV file with duplicate prevention"""
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)

            # Load existing businesses from file
            existing_businesses = []
            existing_names = set()

            if os.path.exists(filename):
                try:
                    with open(filename, mode="r", newline="", encoding="utf-8") as f:
                        reader = tivare.DictReader(f)
                        for row in reader:
                            existing_businesses.append(row)
                            existing_names.add(row['name'].strip().lower())
                    print(f"📂 Loaded {len(existing_businesses)} existing businesses from {filename}")
                except Exception as e:
                    print(f"⚠️ Could not read existing file: {e}")
                    existing_businesses = []
                    existing_names = set()

            # Filter out duplicates from current results
            new_businesses = []
            duplicate_count = 0

            for business in self.results:
                business_name_lower = business['name'].strip().lower()
                if business_name_lower not in existing_names:
                    new_businesses.append(business)
                    existing_names.add(business_name_lower)
                else:
                    duplicate_count += 1

            # Combine existing and new businesses
            all_businesses = existing_businesses + new_businesses

            # Save the merged data
            with open(filename, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["name", "website", "phone", "address", "rating", "review_count"])
                writer.writeheader()
                writer.writerows(all_businesses)

            print(f"💾 Results saved to {filename}")
            print(f"   📊 {len(new_businesses)} new businesses added")
            print(f"   📈 Total businesses in file: {len(all_businesses)}")
            if duplicate_count > 0:
                print(f"   🔄 {duplicate_count} duplicates avoided")

        except Exception as e:
            print(f"❌ Error saving to CSV: {e}")

    def reset_pagination_for_query(self, query):
        """Reset pagination state for a specific query"""
        if query in self.pagination_state:
            del self.pagination_state[query]
            self.save_pagination_state()
            print(f"🔄 Reset pagination state for query: {query}")

    def clear_all_pagination(self):
        """Clear all pagination state"""
        self.pagination_state = {}
        self.save_pagination_state()
        print("🔄 Cleared all pagination state")

    def print_results(self):
        """Print all results to console"""
        print(f"\n📊 SCRAPED RESULTS ({len(self.results)} businesses):")
        print("=" * 80)

        send_scraping_update("Google map search completed", f"SCRAPED RESULTS ({len(self.results)} businesses)")
        for i, business in enumerate(self.results, 1):
            print(f"{i:2d}. {business['name']}")
            print(f"    🌐 {business['website'] or 'No website found'}")
            print(f"     📞 {business['phone'] or 'No phone found'}")
            print(f"     📌 {business['address'] or 'No address found'}")

            print()

    def print_unvisited_summary(self):
        """Print summary of unvisited URLs"""
        unvisited_count = len(self.all_discovered_urls - self.visited_urls)
        print(f"\n📋 UNVISITED URLS SUMMARY:")
        print(f"🔍 Total discovered: {len(self.all_discovered_urls)}")
        print(f"✅ Visited: {len(self.visited_urls)}")
        print(f"❌ Unvisited: {unvisited_count}")

        if unvisited_count > 0:
            print(f"\n⚠️ {unvisited_count} URLs remain unvisited. Run with clean_sweep=True to process them.")


def google_map(niche: str,location: str, max_results: int = 100, clean_sweep: bool = True):
    scraper = MapsBusinessScraper(headless=True)

    query = f"{niche} in {location}"
    output_path = f"csv-json/{query.replace(' ', '_')}.csv"

    scraper.scrape(
        query=query,
        max_results=max_results,
        output_csv=output_path,
        continue_from_last=True,
        clean_sweep=clean_sweep
    )

    return output_path  # or scraper.print_results() if preferred


# Still allows terminal usage:
if __name__ == "__main__":
    import sys
    niche = sys.argv[1] if len(sys.argv) > 1 else "fitness"
    google_map(niche)