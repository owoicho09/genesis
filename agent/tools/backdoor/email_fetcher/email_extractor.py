"""
Refactored Business Information Extractor
A modular, maintainable email and business information scraping system.
"""

import os
import re
import sys
import time
import random
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import List, Set, Optional, Dict, Tuple, Protocol
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.validators import validate_email


# ==================== Configuration ====================

@dataclass
class ScrapingConfig:
    """Configuration settings for the scraper"""
    user_agents: List[str]
    skip_domains: Set[str]
    contact_paths: List[str]
    business_keywords: List[str]
    email_patterns: List[str]
    request_timeout: int = 15
    min_delay: float = 1.0
    max_delay: float = 3.0
    max_workers: int = 5
    max_contact_pages: int = 2
    max_description_length: int = 300

    @classmethod
    def default(cls) -> 'ScrapingConfig':
        """Create default configuration"""
        return cls(
            user_agents=[
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/537.36 Chrome/113.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0"
            ],
            skip_domains={
                'instagram.com', 'facebook.com', 'twitter.com', 'tiktok.com', 'youtube.com',
                'linkedin.com', 'pinterest.com', 'snapchat.com', 'whatsapp.com', 'telegram.org',
                'google.com', 'apple.com', 'amazon.com', 'microsoft.com', 'github.com',
                'behance.net', 'dribbble.com', 'vimeo.com', 'soundcloud.com', 'spotify.com',
                'business.whatsapp.com', 'wa.me', 'chat.whatsapp.com', 'api.whatsapp.com',
                'threads.net', 'x.com', 'discord.com', 'reddit.com', 'tumblr.com'
            },
            contact_paths=[
                '/contact', '/contact-us', '/contact-me', '/get-in-touch', '/reach-out',
                '/about', '/about-us', '/about-me', '/bio', '/biography', '/info',
                '/hire-me', '/work-with-me', '/collaborate', '/booking', '/bookings',
                '/press', '/media', '/business', '/partnerships', '/advertise', '/services'
            ],
            business_keywords=[
                'services', 'solutions', 'consulting', 'agency', 'studio', 'company',
                'business', 'professional', 'expert', 'specialist', 'freelancer',
                'founder', 'ceo', 'entrepreneur', 'coach', 'trainer', 'mentor',
                'design', 'development', 'marketing', 'strategy', 'creative',
                'help', 'work with', 'collaborate', 'partner', 'client', 'project'
            ],
            email_patterns=[
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                r'\b[A-Za-z0-9._%+-]+\s*@\s*[A-Za-z0-9.-]+\s*\.\s*[A-Z|a-z]{2,}\b',
                r'\b[A-Za-z0-9._%+-]+\s*\[at\]\s*[A-Za-z0-9.-]+\s*\[\.\]\s*[A-Z|a-z]{2,}\b',
                r'\b[A-Za-z0-9._%+-]+\s*\(at\)\s*[A-Za-z0-9.-]+\s*\(\.\)\s*[A-Z|a-z]{2,}\b',
                r'\b[A-Za-z0-9._%+-]+\s*at\s*[A-Za-z0-9.-]+\s*dot\s*[A-Z|a-z]{2,}\b',
            ]
        )


# ==================== Data Models ====================

@dataclass
class ExtractionResult:
    """Result of email/business information extraction"""
    lead_id: int
    url: str
    emails: Set[str]
    business_description: str
    status: str
    error_message: Optional[str] = None
    extraction_method: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'lead_id': self.lead_id,
            'url': self.url,
            'emails': list(self.emails),
            'business_description': self.business_description,
            'status': self.status,
            'error_message': self.error_message,
            'extraction_method': self.extraction_method
        }


@dataclass
class ScrapingMetrics:
    """Metrics tracking for scraping operations"""
    total_leads: int = 0
    successful_extractions: int = 0
    failed_extractions: int = 0
    database_updates: int = 0
    start_time: float = 0
    end_time: float = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        return (self.successful_extractions / self.total_leads * 100) if self.total_leads > 0 else 0

    @property
    def duration(self) -> float:
        """Calculate total duration in seconds"""
        return self.end_time - self.start_time if self.end_time > 0 else 0


# ==================== Protocols ====================

class LeadProtocol(Protocol):
    """Protocol for Lead model interface"""
    id: int
    username: str
    email: Optional[str]
    external_urls: Optional[str]
    bio: Optional[str]

    def save(self) -> None:
        """Save the lead to database"""
        ...


class LeadRepositoryProtocol(Protocol):
    """Protocol for Lead repository interface"""

    def get_leads_with_external_urls(self) -> List[LeadProtocol]:
        """Get leads that have external URLs but need email extraction"""
        ...

    def update_lead(self, lead_id: int, emails: Set[str], business_description: str) -> bool:
        """Update lead with extracted information"""
        ...


# ==================== Utilities ====================

class EmailValidator:
    """Email validation utilities"""

    SPAM_PATTERNS = [
        'example.com', 'test.com', 'domain.com', 'yoursite.com',
        'noreply', 'no-reply', 'donotreply'
    ]

    @staticmethod
    def normalize_email(email: str) -> str:
        """Normalize email addresses from obfuscated formats"""
        email = email.lower().strip()

        # Handle obfuscated formats
        replacements = [
            (r'\s*\[at\]\s*', '@'),
            (r'\s*\(at\)\s*', '@'),
            (r'\s*at\s*', '@'),
            (r'\s*\[\.\]\s*', '.'),
            (r'\s*\(\.\)\s*', '.'),
            (r'\s*dot\s*', '.'),
            (r'\s+', '')
        ]

        for pattern, replacement in replacements:
            email = re.sub(pattern, replacement, email)

        return email

    @classmethod
    def is_valid_email(cls, email: str) -> bool:
        """Validate email address"""
        try:
            validate_email(email)

            domain = email.split('@')[1].lower()

            # Skip spam/placeholder emails
            if any(pattern in email.lower() for pattern in cls.SPAM_PATTERNS):
                return False

            # Validate domain format
            if not re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain):
                return False

            return True

        except (ValidationError, IndexError):
            return False


class URLValidator:
    """URL validation utilities"""

    def __init__(self, skip_domains: Set[str]):
        self.skip_domains = skip_domains

    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and not in skip list"""
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower().replace('www.', '')

            return not any(skip_domain in domain for skip_domain in self.skip_domains)

        except Exception:
            return False

    def normalize_url(self, url: str) -> str:
        """Normalize URL format"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url


# ==================== Extractors ====================

class EmailExtractor:
    """Email extraction from text and HTML"""

    def __init__(self, config: ScrapingConfig):
        self.config = config
        self.validator = EmailValidator()

    def extract_from_text(self, text: str) -> Set[str]:
        """Extract emails from text using multiple patterns"""
        emails = set()

        for pattern in self.config.email_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                normalized = self.validator.normalize_email(match)
                if self.validator.is_valid_email(normalized):
                    emails.add(normalized)
        print('Extracted email--',emails)
        return emails

    def extract_from_html(self, soup: BeautifulSoup) -> Set[str]:
        """Extract emails from HTML content"""
        emails = set()

        # Extract from text content
        text_content = soup.get_text()
        emails.update(self.extract_from_text(text_content))

        # Extract from mailto links
        mailto_links = soup.find_all('a', href=re.compile(r'^mailto:', re.I))
        for link in mailto_links:
            href = link.get('href', '')
            if href.startswith('mailto:'):
                email = href.replace('mailto:', '').split('?')[0]
                normalized = self.validator.normalize_email(email)
                if self.validator.is_valid_email(normalized):
                    emails.add(normalized)
            print('No email found with mailto link')
        print(f"[EXTRACT] Extracting from mailto links...{emails}")

        return emails


class BusinessDescriptionExtractor:
    """Business description extraction from HTML"""

    def __init__(self, config: ScrapingConfig):
        self.config = config

    def extract_from_html(self, soup: BeautifulSoup) -> str:
        """Extract business description from HTML"""
        descriptions = []

        # Strategy 1: Meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            descriptions.append(meta_desc['content'].strip())

        # Strategy 2: Business sections
        business_sections = soup.find_all(
            ['div', 'section', 'p', 'span'],
            class_=re.compile(r'about|description|bio|intro|services|business|hero|banner', re.I)
        )

        for section in business_sections:
            text = section.get_text().strip()
            if self._is_valid_description(text):
                descriptions.append(text)

        # Strategy 3: Headings with business content
        headings = soup.find_all(['h1', 'h2', 'h3'])
        for heading in headings:
            text = heading.get_text().strip()
            if any(keyword in text.lower() for keyword in self.config.business_keywords):
                next_element = heading.find_next_sibling(['p', 'div'])
                if next_element:
                    desc_text = next_element.get_text().strip()
                    if self._is_valid_description(desc_text):
                        descriptions.append(desc_text)

        # Strategy 4: First meaningful paragraph
        if not descriptions:
            paragraphs = soup.find_all('p')
            for p in paragraphs:
                text = p.get_text().strip()
                if len(text) > 50 and len(text) < 400:
                    descriptions.append(text)
                    break

        return self._select_best_description(descriptions)

    def _is_valid_description(self, text: str) -> bool:
        """Check if text is a valid business description"""
        return (text and
                20 < len(text) < 500 and
                any(keyword in text.lower() for keyword in self.config.business_keywords))

    def _select_best_description(self, descriptions: List[str]) -> str:
        """Select the best description from candidates"""
        if not descriptions:
            print('No description found for this lead')
            return ""

        # Prefer descriptions with business keywords
        business_descriptions = [
            desc for desc in descriptions
            if any(keyword in desc.lower() for keyword in self.config.business_keywords)
        ]

        if business_descriptions:
            print('Most prefered description selected')
            return business_descriptions[0][:self.config.max_description_length]
        else:
            return descriptions[0][:self.config.max_description_length]


# ==================== Web Scraper ====================

class WebScraper:
    """Web scraping functionality"""

    def __init__(self, config: ScrapingConfig):
        self.config = config
        self.session = self._create_session()
        self.url_validator = URLValidator(config.skip_domains)
        self.email_extractor = EmailExtractor(config)
        self.description_extractor = BusinessDescriptionExtractor(config)

    def _create_session(self) -> requests.Session:
        """Create configured requests session"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': random.choice(self.config.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        return session

    def scrape_url(self, url: str) -> Tuple[Set[str], str, str]:
        """Scrape URL for emails and business description"""
        url = self.url_validator.normalize_url(url)

        if not self.url_validator.is_valid_url(url):
            return set(), "", f"Invalid or skipped URL: {url}"

        try:
            # Add respectful delay
            time.sleep(random.uniform(self.config.min_delay, self.config.max_delay))

            response = self.session.get(url, timeout=self.config.request_timeout, allow_redirects=True)
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' not in content_type:
                return set(), "", f"Non-HTML content: {content_type}"

            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract information
            emails = self.email_extractor.extract_from_html(soup)
            business_desc = self.description_extractor.extract_from_html(soup)
            print(f'Extracting infomation{emails}{business_desc}')
            # Try contact pages if no emails found
            if not emails:
                contact_emails, contact_desc = self._scrape_contact_pages(soup, url)
                emails.update(contact_emails)
                if not business_desc and contact_desc:
                    business_desc = contact_desc
            print('successful')
            return emails, business_desc, "Success"

        except requests.RequestException as e:
            return set(), "", f"Request error: {str(e)}"
        except Exception as e:
            return set(), "", f"General error: {str(e)}"

    def _scrape_contact_pages(self, soup: BeautifulSoup, base_url: str) -> Tuple[Set[str], str]:
        """Scrape contact pages for additional information"""
        contact_links = self._find_contact_links(soup, base_url)
        all_emails = set()
        business_desc = ""

        for contact_url in contact_links[:self.config.max_contact_pages]:
            try:
                time.sleep(random.uniform(1, 2))
                response = self.session.get(contact_url, timeout=10)
                response.raise_for_status()

                contact_soup = BeautifulSoup(response.text, 'html.parser')
                emails = self.email_extractor.extract_from_html(contact_soup)
                desc = self.description_extractor.extract_from_html(contact_soup)

                all_emails.update(emails)
                if not business_desc and desc:
                    business_desc = desc

                if emails:
                    break

            except Exception as e:
                logging.warning(f"Error scraping contact page {contact_url}: {e}")
                continue

        return all_emails, business_desc

    def _find_contact_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find contact page links"""
        contact_links = []

        for link in soup.find_all('a', href=True):
            href = link.get('href').lower()
            link_text = link.get_text().lower()

            if (any(path in href for path in self.config.contact_paths) or
                    any(word in link_text for word in ['contact', 'about', 'hire', 'work'])):
                full_url = urljoin(base_url, link.get('href'))
                contact_links.append(full_url)

        return contact_links


# ==================== Repository ====================

class DjangoLeadRepository:
    """Django-based lead repository implementation"""

    def __init__(self):
        self._setup_django()

    def _setup_django(self):
        """Setup Django environment"""
        PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
        sys.path.insert(0, PROJECT_ROOT)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

        try:
            import django
            django.setup()
            from agent.models import Lead
            self.Lead = Lead
            logging.info("Django setup successful")
        except Exception as e:
            logging.error(f"Django setup failed: {e}")
            sys.exit(1)

    def get_leads_with_external_urls(self) -> List[LeadProtocol]:
        """Get leads with external URLs but no valid email"""
        leads = self.Lead.objects.filter(
            external_urls__isnull=False,
            external_urls__gt=''
        ).exclude(external_urls__exact='')

        # Filter out leads with valid emails
        filtered_leads = []
        for lead in leads:
            if (not lead.email or
                    lead.email.endswith('@instagram.placeholder') or
                    'placeholder' in lead.email.lower()):
                filtered_leads.append(lead)
        return filtered_leads

    def update_lead(self, lead_id: int, emails: Set[str], business_description: str) -> bool:
        """Update lead with extracted information"""
        try:
            with transaction.atomic():
                lead = self.Lead.objects.get(id=lead_id)
                updated = False

                # Update email if found
                if emails:
                    primary_email = list(emails)[0]

                    # Check for existing email
                    existing_lead = self.Lead.objects.filter(
                        email=primary_email
                    ).exclude(id=lead_id).first()

                    if not existing_lead:
                        lead.email = primary_email
                        updated = True
                        logging.info(f"Updated email for lead {lead_id}: {primary_email}")

                # Update business description
                if business_description:
                    if hasattr(lead, 'business_description'):
                        lead.business_description = business_description
                        updated = True
                    elif hasattr(lead, 'bio'):
                        current_bio = lead.bio or ""
                        if business_description not in current_bio:
                            lead.bio = f"{current_bio}\n\nBusiness: {business_description}".strip()
                            updated = True

                if updated:
                    print('Database updated successfully')
                    lead.save()
                    return True

        except self.Lead.DoesNotExist:
            logging.error(f"Lead {lead_id} not found")
        except Exception as e:
            logging.error(f"Error updating lead {lead_id}: {e}")

        return False


# ==================== Main Service ====================

class BusinessInfoExtractionService:
    """Main service for business information extraction"""

    def __init__(self, config: ScrapingConfig, repository: LeadRepositoryProtocol):
        self.config = config
        self.repository = repository
        self.scraper = WebScraper(config)
        self.metrics = ScrapingMetrics()
        self.logger = logging.getLogger(__name__)

    def extract_business_info(self) -> List[ExtractionResult]:
        """Extract business information for all leads"""
        self.metrics.start_time = time.time()

        # Get leads to process
        leads = self.repository.get_leads_with_external_urls()
        self.metrics.total_leads = len(leads)

        self.logger.info(f"Starting extraction for {len(leads)} leads")

        results = []

        # Process leads
        for i, lead in enumerate(leads, 1):
            self.logger.info(f"Processing lead {i}/{len(leads)}: {lead.username}")

            try:
                result = self._process_lead(lead)
                results.append(result)
                print(f'Processed leads✅{result}')

                # Update database if successful
                if result.status == "Success" and (result.emails or result.business_description):
                    if self.repository.update_lead(result.lead_id, result.emails, result.business_description):
                        self.metrics.database_updates += 1
                        print(f'database updated successfully{result.lead_id},email-->{result.emails},descrip-->{result.business_description}')
                    self.metrics.successful_extractions += 1
                else:
                    self.metrics.failed_extractions += 1

                # Add delay between requests
                if i < len(leads):
                    delay = random.uniform(self.config.min_delay, self.config.max_delay)
                    time.sleep(delay)

            except Exception as e:
                self.logger.error(f"Error processing lead {lead.id}: {e}")
                results.append(ExtractionResult(
                    lead_id=lead.id,
                    url="",
                    emails=set(),
                    business_description="",
                    status="Error",
                    error_message=str(e)
                ))
                self.metrics.failed_extractions += 1

        self.metrics.end_time = time.time()
        self._log_metrics()

        return results

    def _process_lead(self, lead: LeadProtocol) -> ExtractionResult:
        """Process a single lead"""
        if not lead.external_urls:
            return ExtractionResult(
                lead_id=lead.id,
                url="",
                emails=set(),
                business_description="",
                status="No external URLs"
            )

        # Parse URLs
        urls = [url.strip() for url in lead.external_urls.split('|') if url.strip()]

        all_emails = set()
        business_description = ""
        successful_url = None

        for url in urls:
            if not self._is_relevant_site(url):
                continue

            try:
                emails, desc, status = self.scraper.scrape_url(url)

                if emails or desc:
                    all_emails.update(emails)
                    print(f'All emails{all_emails}')
                    if desc and not business_description:
                        business_description = desc
                    successful_url = url
                    break

            except Exception as e:
                self.logger.warning(f"Error processing URL {url}: {e}")
                continue

        if all_emails or business_description:
            print('✅success in Extraction')
            return ExtractionResult(
                lead_id=lead.id,
                url=successful_url,
                emails=all_emails,
                business_description=business_description,
                status="Success"
            )
        else:
            print('❌unsuccessful in Extraction no result found')
            return ExtractionResult(
                lead_id=lead.id,
                url=urls[0] if urls else "",
                emails=set(),
                business_description="",
                status="No information found"
            )

    def _is_relevant_site(self, url: str) -> bool:
        """Check if URL is from a relevant site"""
        return self.scraper.url_validator.is_valid_url(url)

    def _log_metrics(self):
        """Log extraction metrics"""
        self.logger.info("Extraction Summary:")
        self.logger.info(f"  Total leads: {self.metrics.total_leads}")
        self.logger.info(f"  Successful extractions: {self.metrics.successful_extractions}")
        self.logger.info(f"  Failed extractions: {self.metrics.failed_extractions}")
        self.logger.info(f"  Database updates: {self.metrics.database_updates}")
        self.logger.info(f"  Success rate: {self.metrics.success_rate:.1f}%")
        self.logger.info(f"  Duration: {self.metrics.duration:.1f}s")


# ==================== Results Manager ====================

class ResultsManager:
    """Manage extraction results"""

    @staticmethod
    def save_to_file(results: List[ExtractionResult], filename: str = "extraction_results.json"):
        """Save results to JSON file"""
        try:
            results_data = [result.to_dict() for result in results]

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results_data, f, indent=2, ensure_ascii=False)

            logging.info(f"Results saved to {filename}")

        except Exception as e:
            logging.error(f"Error saving results: {e}")
            raise

    @staticmethod
    def load_from_file(filename: str) -> List[ExtractionResult]:
        """Load results from JSON file"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)

            results = []
            for item in data:
                result = ExtractionResult(
                    lead_id=item['lead_id'],
                    url=item['url'],
                    emails=set(item['emails']),
                    business_description=item['business_description'],
                    status=item['status'],
                    error_message=item.get('error_message'),
                    extraction_method=item.get('extraction_method')
                )
                results.append(result)

            return results

        except Exception as e:
            logging.error(f"Error loading results: {e}")
            raise


# ==================== Logging Setup ====================

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('email_scraper.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    # Fix Windows console Unicode issues
    if sys.platform == 'win32':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)


# ==================== Main Function ====================

def extract_business_info_tool():
    """Main function"""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting Business Information Extractor")
    logger.info("=" * 50)

    try:
        # Initialize components
        config = ScrapingConfig.default()
        repository = DjangoLeadRepository()
        service = BusinessInfoExtractionService(config, repository)

        # Extract business information
        results = service.extract_business_info()

        # Save results
        ResultsManager.save_to_file(results)

        # Show sample results
        emails_str = "None extracted"  # Default fallback
        success_results = [r for r in results if r.emails or r.business_description]
        if success_results:
            logger.info("\nSample successful results:")
            for result in success_results[:5]:
                emails_str = ', '.join(list(result.emails)[:2]) if result.emails else "None"
                desc_preview = (result.business_description[:100] + "..."
                                if len(result.business_description) > 100
                                else result.business_description)
                logger.info(f"  Lead {result.lead_id}: {emails_str} | {desc_preview}")
        print(f'Extraction completed successfully {emails_str}')
        logger.info("Extraction completed successfully!")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    extract_business_info_tool()


