#!/usr/bin/env python3
"""
Universal Bio/Description Scraper
=================================
Fetches bios/descriptions from various social media platforms and websites
for leads with emails to enable personalized outreach.
"""

import os
import sys
import django
import time
from tqdm import tqdm
import random
import logging
from urllib.parse import urlparse
from typing import Optional, Dict, Any

from playwright.sync_api import sync_playwright, Page, BrowserContext

# --- Django Setup ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from agent.models import Lead

# --- Configuration ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.71 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_6_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

# Platform-specific selectors
PLATFORM_SELECTORS = {
    'instagram': {
        'bio_selectors': [
            'header section div:not([class])',
            'header section div[data-testid="bio"]',
            'header section span',
            'article header section div'
        ],
        'wait_selector': 'main',
        'popup_selectors': [
            "div[role=dialog] button",
            "button:has-text('Not Now')",
            "[aria-label='Close']",
        ]
    },
    'twitter': {
        'bio_selectors': [
            '[data-testid="UserDescription"]',
            '[data-testid="UserName"] + div',
            'div[dir="auto"] span'
        ],
        'wait_selector': 'main',
        'popup_selectors': [
            '[aria-label="Close"]',
            'div[role="button"]:has-text("Not now")'
        ]
    },
    'linkedin': {
        'bio_selectors': [
            '.pv-text-details__about-this-profile-entrypoint',
            '.pv-about-section .pv-about__summary-text',
            '.top-card-layout__headline',
            '.pv-entity__summary-info h2'
        ],
        'wait_selector': 'main',
        'popup_selectors': [
            'button[aria-label="Dismiss"]',
            '.msg-overlay-bubble-header__control'
        ]
    },
    'facebook': {
        'bio_selectors': [
            '[data-overviewsection="about"] span',
            '.profileHighlightsSection span',
            '.aboutSection span'
        ],
        'wait_selector': 'main',
        'popup_selectors': [
            '[aria-label="Close"]',
            'div[role="button"]:has-text("Not Now")'
        ]
    },
    'generic': {
        'bio_selectors': [
            'meta[name="description"]',
            'meta[property="og:description"]',
            'meta[name="twitter:description"]',
            '.bio', '.about', '.description',
            'h1', 'h2', '.tagline', '.subtitle'
        ],
        'wait_selector': 'body',
        'popup_selectors': []
    }
}

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bio_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def get_platform_from_url(url: str) -> str:
    """Determine the platform from URL"""
    domain = urlparse(url).netloc.lower()

    if 'instagram.com' in domain or 'instagr.am' in domain:
        return 'instagram'
    elif 'twitter.com' in domain or 'x.com' in domain:
        return 'twitter'
    elif 'linkedin.com' in domain:
        return 'linkedin'
    elif 'facebook.com' in domain or 'fb.com' in domain:
        return 'facebook'
    else:
        return 'generic'

def normalize_url(url: str) -> str:
    """Normalize URL format"""
    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url
    return url

def wait_for_page_load(page: Page, platform: str, timeout: int = 15000) -> bool:
    """Wait for page to load based on platform"""
    wait_selector = PLATFORM_SELECTORS[platform]['wait_selector']

    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
        page.wait_for_selector(wait_selector, timeout=8000)
        page.wait_for_timeout(random.randint(2000, 4000))
        return True
    except:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout)
            page.wait_for_timeout(random.randint(3000, 5000))
            return True
        except:
            logger.warning(f"Failed to wait for page load on {platform}")
            return False

def dismiss_popups(page: Page, platform: str) -> None:
    """Dismiss common popups based on platform"""
    popup_selectors = PLATFORM_SELECTORS[platform]['popup_selectors']

    for selector in popup_selectors:
        try:
            element = page.locator(selector).first
            if element.is_visible(timeout=2000):
                element.click(timeout=2000)
                page.wait_for_timeout(1000)
                logger.info(f"Dismissed popup with selector: {selector}")
                break
        except:
            continue

def extract_description(page: Page, platform: str) -> Optional[str]:
    """Extract bio/description based on platform"""
    selectors = PLATFORM_SELECTORS[platform]['bio_selectors']

    for selector in selectors:
        try:
            if platform == 'generic' and selector.startswith('meta'):
                # Handle meta tags differently
                element = page.locator(selector)
                if element.count() > 0:
                    content = element.get_attribute('content')
                    if content and len(content.strip()) > 10:
                        return content.strip()
            else:
                # Handle regular selectors
                elements = page.locator(selector).all()
                for element in elements:
                    if element.is_visible(timeout=1000):
                        text = element.text_content().strip()
                        if text and len(text) > 15 and not text.startswith('@'):
                            return text
        except Exception as e:
            logger.debug(f"Error with selector {selector}: {e}")
            continue

    return None

def create_browser_context(browser, platform: str) -> BrowserContext:
    """Create browser context with appropriate settings"""
    user_agent = random.choice(USER_AGENTS)

    context_options = {
        'user_agent': user_agent,
        'viewport': {'width': 1920, 'height': 1080},
        'extra_http_headers': {
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    }

    # Platform-specific settings
    if platform == 'linkedin':
        context_options['extra_http_headers']['Sec-Fetch-Site'] = 'same-origin'
        context_options['extra_http_headers']['Sec-Fetch-Mode'] = 'navigate'

    return browser.new_context(**context_options)

def scrape_single_lead(lead: Lead, browser) -> bool:
    """Scrape bio/description for a single lead"""
    try:
        url = normalize_url(lead.source_url)
        platform = get_platform_from_url(url)

        context = create_browser_context(browser, platform)
        page = context.new_page()

        logger.info(f"Scraping {platform} - {url}")

        # Navigate to page
        page.goto(url, timeout=20000, wait_until='domcontentloaded')

        # Wait for page load
        if not wait_for_page_load(page, platform):
            logger.warning(f"Page load timeout for {url}")
            return False

        # Dismiss popups
        dismiss_popups(page, platform)

        # Extract description
        description = extract_description(page, platform)

        if description:
            lead.business_description = description
            lead.save(update_fields=["business_description"])
            logger.info(f" Updated bio for {lead.username or lead.id}: {description[:50]}...")
            return True
        else:
            logger.warning(f"️ No bio found for {lead.username or lead.id}")
            return False

    except Exception as e:
        logger.error(f" Failed to process {lead.source_url}: {str(e)}")
        return False
    finally:
        try:
            page.close()
            context.close()
        except:
            pass

def get_leads_for_scraping() -> list:
    """Get leads that need bio scraping"""
    return list(
        Lead.objects.filter(
            email__isnull=False,
            source_url__isnull=False,
            business_description__isnull=True  # Only leads without existing descriptions
        ).exclude(
            email="",
            source_url=""
        ).order_by("-created_at")
    )

def update_leads_bios(max_leads: Optional[int] = None) -> Dict[str, Any]:
    """Main function to update lead bios"""
    leads = get_leads_for_scraping()

    if not leads:
        logger.info(" No leads found that need bio scraping.")
        return {"processed": 0, "successful": 0, "failed": 0}

    if max_leads:
        leads = leads[:max_leads]

    logger.info(f" Found {len(leads)} leads to process")

    stats = {"processed": 0, "successful": 0, "failed": 0}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )

        try:
            for lead in tqdm(leads, desc="🔍 Scraping bios"):
                stats["processed"] += 1

                if scrape_single_lead(lead, browser):
                    stats["successful"] += 1
                else:
                    stats["failed"] += 1

                # Random delay between requests
                delay = random.uniform(3, 8)
                time.sleep(delay)

        finally:
            browser.close()

    logger.info(f" Finished scraping. Processed: {stats['processed']}, "
                f"Successful: {stats['successful']}, Failed: {stats['failed']}")

    return stats

# --- Main Execution ---
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Scrape bios/descriptions for leads')
    parser.add_argument('--max-leads', type=int, help='Maximum number of leads to process')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        stats = update_leads_bios(max_leads=args.max_leads)
        print(f"\n Final Statistics:")
        print(f"   Processed: {stats['processed']}")
        print(f"   Successful: {stats['successful']}")
        print(f"   Failed: {stats['failed']}")

    except KeyboardInterrupt:
        logger.info("❌ Scraping interrupted by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)