import csv
import json
import time
import os
from urllib.parse import quote, urlparse, unquote
from playwright.sync_api import sync_playwright
import re
from agent.tools.utils.send_email_update import send_scraping_update
import sys
sys.stdout.reconfigure(encoding='utf-8')


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

    def extract_business_info(self, page):
        """Extract business name and website from the current page"""
        business_info = {"name": "", "website": ""}

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

        # First, discover all cards
        discovered_urls = self.discover_all_cards(page)

        if not discovered_urls:
            print("❌ No cards discovered")
            return 0

        # Get unvisited cards
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
                # Navigate directly to the card
                if self.navigate_to_card_directly(page, card_url):

                    # Mark as visited
                    self.visited_urls.add(card_url)

                    # Extract business information
                    business_info = self.extract_business_info(page)

                    # Check for duplicates
                    business_name_lower = business_info["name"].strip().lower()
                    if business_name_lower in self.seen_names:
                        print(f"⚠️ Skipping duplicate business: {business_info['name']}")
                        continue

                    if business_info["name"] and business_info["name"] != "Unknown Business":
                        self.seen_names.add(business_name_lower)
                        self.results.append(business_info)
                        processed_count += 1

                        print(f"✅ SUCCESS! Business {processed_count} saved:")
                        print(f"   📍 Name: {business_info['name']}")
                        print(f"   🌐 Website: {business_info['website'] or 'Not found'}")

                        # Save intermediate results every 3 businesses
                        if processed_count % 3 == 0:
                            self.save_to_csv(output_csv)
                            self.save_visited_urls()
                            print(f"💾 Intermediate save completed")
                    else:
                        print("⚠️ Could not extract valid business name")

                else:
                    print("❌ Failed to navigate to card")

            except Exception as e:
                print(f"❌ Error processing card: {e}")

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
                        reader = csv.DictReader(f)
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
                writer = csv.DictWriter(f, fieldnames=["name", "website"])
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


def google_map(niche: str,location: str, max_results: int = 70, clean_sweep: bool = True):
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