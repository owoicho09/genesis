#!/usr/bin/env python3
"""
Django Email Validation & Cleaning Script - Refactored
=====================================================

Production-ready script to validate and clean scraped emails from Lead model.
Removes placeholder, fake, malformed, and high-bounce emails before outreach.
Includes API validation with fallback mechanisms.

Usage:
    python manage.py shell < email_cleaner.py
    # OR
    python email_cleaner.py --dry-run
    python email_cleaner.py --api-validate --batch-size 500
"""

import os
import re
import sys
import time
import logging
import argparse
import requests
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

# Django imports
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
# Django Setup
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")



# DNS validation
try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False
    print("Warning: dnspython not installed. MX record validation disabled.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_cleaning.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

try:
    import django

    django.setup()
    from agent.models import Lead

    logging.info("Django setup successful")
except Exception as e:
    logging.error(f"Django setup failed: {e}")
    sys.exit(1)

@dataclass
class ValidationStats:
    """Statistics tracking for email validation"""
    total_processed: int = 0
    valid_emails: int = 0
    invalid_format: int = 0
    blacklisted: int = 0
    suspicious_tld: int = 0
    too_long: int = 0
    corrected_typos: int = 0
    cleaned: int = 0
    api_verified: int = 0
    api_failed: int = 0
    mx_record_failed: int = 0
    rate_limited: int = 0

    def get_valid_percentage(self) -> float:
        """Calculate percentage of valid emails"""
        if self.total_processed == 0:
            return 0.0
        return (self.valid_emails / self.total_processed) * 100


@dataclass
class ValidationResult:
    """Result of email validation"""
    is_valid: bool
    reason: str
    corrected_email: Optional[str] = None
    api_verified: bool = False
    confidence_score: float = 0.0


class EmailValidationConfig:
    """Configuration for email validation"""

    # Enhanced email validation patterns
    EMAIL_REGEX = re.compile(
        r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
    )

    # Comprehensive blacklist for fake/placeholder emails
    BLACKLISTED_SUBSTRINGS = [
        # Placeholder patterns
        "placeholder", "example", "sample", "demo", "dummy", "fake", "test",
        "temp", "temporary", "invalid", "none", "null", "undefined",

        # No-reply patterns
        "noreply", "donotreply", "no-reply", "do-not-reply", "noreplies",
        "no_reply", "donot_reply", "noreply@", "donotreply@",

        # Common fake domains
        "@fake", "@test", "@example", "@sample", "@demo", "@dummy",
        "@tempmail", "@mailinator", "@guerrillamail", "@10minutemail",
        "@throwaway", "@disposable", "@trashmail", "@spam4.me",
        "@yopmail", "@maildrop", "@sharklasers", "@grr.la",

        # Generic placeholders
        "@domain", "@company", "@website", "@site", "@business",
        "@yourdomain", "@yourcompany", "@yoursite", "@yourwebsite",
        "@email", "@mail", "@contact", "@info", "@support",

        # File extensions that shouldn't be in emails
        ".jpg", ".png", ".gif", ".pdf", ".doc", ".docx", ".txt",
        ".zip", ".rar", ".exe", ".bat", ".sh", ".csv", ".xlsx",

        # Suspicious patterns
        "asdf", "qwerty", "123456", "password", "admin", "root",
        "user", "guest", "anonymous", "default", "system",
        "lorem", "ipsum", "dolor", "sit", "amet",

        # High-bounce indicators
        "bounce", "bounced", "undeliverable", "rejected", "blocked",
        "spam", "abuse", "postmaster", "mailer-daemon",

        # Social media usernames (often not real emails)
        "@facebook", "@twitter", "@instagram", "@linkedin", "@tiktok",
        "@snapchat", "@youtube", "@reddit", "@discord", "@whatsapp"
    ]

    # Suspicious TLDs that often indicate fake emails
    SUSPICIOUS_TLDS = [
        ".test", ".invalid", ".localhost", ".local", ".example",
        ".placeholder", ".fake", ".dummy", ".temp", ".dev"
    ]

    # Common typos in popular domains
    DOMAIN_TYPOS = {
        "gmial.com": "gmail.com",
        "gmai.com": "gmail.com",
        "gmall.com": "gmail.com",
        "gmeil.com": "gmail.com",
        "yahooo.com": "yahoo.com",
        "yaho.com": "yahoo.com",
        "yhaoo.com": "yahoo.com",
        "hotmial.com": "hotmail.com",
        "hotmali.com": "hotmail.com",
        "hotmeil.com": "hotmail.com",
        "outlok.com": "outlook.com",
        "outloo.com": "outlook.com",
        "outlokk.com": "outlook.com",
        "aol.co": "aol.com",
        "comcast.ent": "comcast.net",
        "verizon.ent": "verizon.net"
    }

    # API configurations
    MAILBOXLAYER_API_URL = "https://apilayer.net/api/check"
    API_TIMEOUT = 10
    API_RETRY_COUNT = 3
    API_RATE_LIMIT_DELAY = 0.1  # seconds between API calls


class DNSValidator:
    """DNS-based email validation"""

    @staticmethod
    def has_mx_record(domain: str) -> bool:
        """Check if domain has a valid MX record"""
        if not DNS_AVAILABLE:
            return True  # Skip validation if DNS library not available

        try:
            answers = dns.resolver.resolve(domain, 'MX', lifetime=5)
            return len(answers) > 0
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                dns.exception.Timeout, Exception):
            return False

    @staticmethod
    def has_a_record(domain: str) -> bool:
        """Check if domain has a valid A record"""
        if not DNS_AVAILABLE:
            return True

        try:
            answers = dns.resolver.resolve(domain, 'A', lifetime=5)
            return len(answers) > 0
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                dns.exception.Timeout, Exception):
            return False


class APIValidator:
    """API-based email validation with multiple providers"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('mail_box_layer_api_key')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'EmailValidator/1.0',
            'Accept': 'application/json'
        })

    def verify_email_with_mailboxlayer(self, email: str) -> Tuple[bool, float, str]:
        """
        Verify email using MailboxLayer API

        Returns:
            (is_valid, confidence_score, reason)
        """
        if not self.api_key:
            return False, 0.0, "No API key provided"

        params = {
            "access_key": self.api_key,
            "email": email,
            "smtp": 1,
            "format": 1
        }

        for attempt in range(EmailValidationConfig.API_RETRY_COUNT):
            try:
                response = self.session.get(
                    EmailValidationConfig.MAILBOXLAYER_API_URL,
                    params=params,
                    timeout=EmailValidationConfig.API_TIMEOUT
                )

                if response.status_code == 429:  # Rate limited
                    time.sleep(EmailValidationConfig.API_RATE_LIMIT_DELAY * (2 ** attempt))
                    continue

                response.raise_for_status()
                data = response.json()

                # Check for API errors
                if 'error' in data:
                    return False, 0.0, f"API Error: {data['error'].get('info', 'Unknown')}"

                # Validate response structure
                required_fields = ['smtp_check', 'format_valid', 'score']
                if not all(field in data for field in required_fields):
                    return False, 0.0, "Invalid API response structure"

                # Calculate validation result
                smtp_valid = data.get('smtp_check', False)
                format_valid = data.get('format_valid', False)
                score = data.get('score', 0.0)

                # More sophisticated validation logic
                is_valid = (
                        smtp_valid and
                        format_valid and
                        score >= 0.6 and
                        not data.get('disposable', False) and
                        not data.get('catch_all', False)
                )

                confidence = min(score, 1.0) if score else 0.0
                reason = "API validated" if is_valid else f"API rejected (score: {score})"

                return is_valid, confidence, reason

            except requests.exceptions.RequestException as e:
                logger.warning(f"API request failed (attempt {attempt + 1}): {str(e)}")
                if attempt == EmailValidationConfig.API_RETRY_COUNT - 1:
                    return False, 0.0, f"API request failed: {str(e)}"
                time.sleep(EmailValidationConfig.API_RATE_LIMIT_DELAY * (2 ** attempt))

            except Exception as e:
                logger.error(f"Unexpected error during API validation: {str(e)}")
                return False, 0.0, f"Unexpected API error: {str(e)}"

        return False, 0.0, "API validation failed after retries"


class EmailValidator:
    """Comprehensive email validator with multiple validation methods"""

    def __init__(self, use_api: bool = False, api_key: Optional[str] = None):
        self.use_api = use_api
        self.api_validator = APIValidator(api_key) if use_api else None
        self.dns_validator = DNSValidator()
        self.stats = ValidationStats()
        self.config = EmailValidationConfig()

    def normalize_email(self, email: str) -> str:
        """Normalize email for consistent processing"""
        if not email:
            return ""

        # Basic cleaning
        email = email.strip().lower()

        # Remove multiple spaces
        email = re.sub(r'\s+', '', email)

        # Remove common prefixes that might be added during scraping
        prefixes_to_remove = ['email:', 'e-mail:', 'mail:', 'contact:']
        for prefix in prefixes_to_remove:
            if email.startswith(prefix):
                email = email[len(prefix):].strip()

        return email

    def validate_format(self, email: str) -> ValidationResult:
        """Validate email format and basic structure"""
        if not email:
            return ValidationResult(False, "Empty email")

        # Check length (RFC 5321 limits)
        if len(email) > 254:
            return ValidationResult(False, "Email too long")

        # Basic regex validation
        if not self.config.EMAIL_REGEX.match(email):
            return ValidationResult(False, "Invalid format")

        # Django's built-in validation
        try:
            validate_email(email)
        except ValidationError:
            return ValidationResult(False, "Django validation failed")

        return ValidationResult(True, "Format valid")

    def check_blacklist(self, email: str) -> ValidationResult:
        """Check email against blacklist patterns"""
        # Check for blacklisted substrings
        for blacklisted in self.config.BLACKLISTED_SUBSTRINGS:
            if blacklisted in email:
                return ValidationResult(False, f"Contains blacklisted substring: {blacklisted}")

        # Check for suspicious TLDs
        for tld in self.config.SUSPICIOUS_TLDS:
            if email.endswith(tld):
                return ValidationResult(False, f"Suspicious TLD: {tld}")

        # Additional pattern checks
        local_part = email.split('@')[0]

        # Check for too many consecutive dots or special chars
        if '..' in email or '__' in email or '--' in email:
            return ValidationResult(False, "Suspicious character patterns")

        # Check for emails that are just numbers (often fake)
        if local_part.isdigit() and len(local_part) > 10:
            return ValidationResult(False, "Local part is all numbers")

        # Check for emails with only special characters
        if not re.search(r'[a-zA-Z0-9]', local_part):
            return ValidationResult(False, "Local part contains no alphanumeric characters")

        return ValidationResult(True, "Blacklist check passed")

    def check_domain_typos(self, email: str) -> ValidationResult:
        """Check for common domain typos and suggest corrections"""
        domain = email.split('@')[1]

        if domain in self.config.DOMAIN_TYPOS:
            corrected_domain = self.config.DOMAIN_TYPOS[domain]
            corrected_email = email.replace(domain, corrected_domain)
            return ValidationResult(
                True,
                "Domain typo corrected",
                corrected_email=corrected_email
            )

        return ValidationResult(True, "No domain typos detected")

    def validate_dns(self, email: str) -> ValidationResult:
        """Validate email domain using DNS checks"""
        domain = email.split('@')[1]

        # Check for MX record
        if not self.dns_validator.has_mx_record(domain):
            # If no MX record, check for A record as fallback
            if not self.dns_validator.has_a_record(domain):
                return ValidationResult(False, "No MX or A record (non-deliverable domain)")

        return ValidationResult(True, "DNS validation passed")

    def validate_with_api(self, email: str) -> ValidationResult:
        """Validate email using external API"""
        if not self.use_api or not self.api_validator:
            return ValidationResult(True, "API validation skipped")

        try:
            is_valid, confidence, reason = self.api_validator.verify_email_with_mailboxlayer(email)

            if "rate limit" in reason.lower() or "429" in reason:
                self.stats.rate_limited += 1
                return ValidationResult(True, "API rate limited - skipping")

            if is_valid:
                self.stats.api_verified += 1
                return ValidationResult(
                    True,
                    reason,
                    api_verified=True,
                    confidence_score=confidence
                )
            else:
                self.stats.api_failed += 1
                return ValidationResult(False, reason, confidence_score=confidence)

        except Exception as e:
            logger.error(f"API validation error for {email}: {str(e)}")
            return ValidationResult(True, f"API validation error: {str(e)}")

    def validate_email(self, email: str) -> ValidationResult:
        """
        Comprehensive email validation using multiple methods

        Returns:
            ValidationResult with detailed validation information
        """
        # Normalize email
        normalized_email = self.normalize_email(email)

        # Step 1: Format validation
        result = self.validate_format(normalized_email)
        if not result.is_valid:
            return result

        # Step 2: Blacklist check
        result = self.check_blacklist(normalized_email)
        if not result.is_valid:
            return result

        # Step 3: Domain typo check
        result = self.check_domain_typos(normalized_email)
        if result.corrected_email:
            normalized_email = result.corrected_email

        # Step 4: DNS validation
        dns_result = self.validate_dns(normalized_email)
        if not dns_result.is_valid:
            self.stats.mx_record_failed += 1
            return dns_result

        # Step 5: API validation (if enabled)
        if self.use_api:
            api_result = self.validate_with_api(normalized_email)
            if not api_result.is_valid and "rate limit" not in api_result.reason.lower():
                return api_result

            # Merge API results
            result.api_verified = api_result.api_verified
            result.confidence_score = api_result.confidence_score

        # Final result
        return ValidationResult(
            True,
            "Valid",
            corrected_email=result.corrected_email,
            api_verified=result.api_verified,
            confidence_score=result.confidence_score
        )

    def update_stats(self, result: ValidationResult):
        """Update validation statistics"""
        self.stats.total_processed += 1

        if result.is_valid:
            self.stats.valid_emails += 1
            if result.corrected_email:
                self.stats.corrected_typos += 1
        else:
            reason = result.reason.lower()
            if "invalid format" in reason or "django validation" in reason:
                self.stats.invalid_format += 1
            elif "blacklisted" in reason:
                self.stats.blacklisted += 1
            elif "suspicious tld" in reason:
                self.stats.suspicious_tld += 1
            elif "too long" in reason:
                self.stats.too_long += 1
            elif "mx record" in reason:
                self.stats.mx_record_failed += 1

    def print_stats(self):
        """Print comprehensive validation statistics"""
        logger.info("\n" + "="*60)
        logger.info("EMAIL VALIDATION STATISTICS")
        logger.info("="*60)
        logger.info(f"Total processed: {self.stats.total_processed}")
        logger.info(f"Valid emails: {self.stats.valid_emails}")
        logger.info(f"Corrected typos: {self.stats.corrected_typos}")
        logger.info(f"Invalid format: {self.stats.invalid_format}")
        logger.info(f"Blacklisted: {self.stats.blacklisted}")
        logger.info(f"Suspicious TLD: {self.stats.suspicious_tld}")
        logger.info(f"Too long: {self.stats.too_long}")
        logger.info(f"MX record failed: {self.stats.mx_record_failed}")
        logger.info(f"Cleaned/removed: {self.stats.cleaned}")

        if self.use_api:
            logger.info(f"API verified: {self.stats.api_verified}")
            logger.info(f"API failed: {self.stats.api_failed}")
            logger.info(f"Rate limited: {self.stats.rate_limited}")

        valid_percentage = self.stats.get_valid_percentage()
        logger.info(f"Valid email rate: {valid_percentage:.2f}%")
        logger.info("="*60)


@transaction.atomic
def clean_emails(
        dry_run: bool = False,
        use_api: bool = False,
        api_key: Optional[str] = None,
        batch_size: int = 1000,
        max_workers: int = 4
) -> ValidationStats:
    """
    Clean and validate emails in Lead model with advanced options

    Args:
        dry_run: If True, only report what would be cleaned
        use_api: If True, use API validation
        api_key: API key for external validation
        batch_size: Number of leads to process in each batch
        max_workers: Number of threads for parallel processing

    Returns:
        ValidationStats with detailed statistics
    """
    logger.info("Starting email cleaning process...")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE CLEANING'}")
    logger.info(f"API validation: {'ENABLED' if use_api else 'DISABLED'}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Max workers: {max_workers}")

    validator = EmailValidator(use_api=use_api, api_key=api_key)

    # Get all leads with email addresses
    leads = Lead.objects.exclude(email__isnull=True).exclude(email__exact='')
    total_leads = leads.count()

    if total_leads == 0:
        logger.warning("No leads found with email addresses")
        return validator.stats

    logger.info(f"Found {total_leads} leads with email addresses")

    # Process in batches
    processed = 0

    for i in range(0, total_leads, batch_size):
        batch = leads[i:i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(f"Processing batch {batch_num} ({len(batch)} leads)")

        # Process batch
        for lead in batch:
            try:
                result = validator.validate_email(lead.email)
                validator.update_stats(result)

                if not result.is_valid:
                    logger.warning(f"Invalid email: {lead.email} (ID: {lead.id}) - {result.reason}")
                    if not dry_run:
                        lead.email = None
                        lead.save(update_fields=['email'])
                        validator.stats.cleaned += 1

                elif result.corrected_email:
                    logger.info(f"Corrected email: {lead.email} -> {result.corrected_email} (ID: {lead.id})")
                    if not dry_run:
                        lead.email = result.corrected_email
                        lead.save(update_fields=['email'])

                processed += 1

                # Progress indicator
                if processed % 100 == 0:
                    logger.info(f"Processed {processed}/{total_leads} leads...")

                # Rate limiting for API calls
                if use_api and processed % 10 == 0:
                    time.sleep(EmailValidationConfig.API_RATE_LIMIT_DELAY)

            except Exception as e:
                logger.error(f"Error processing lead {lead.id}: {str(e)}")
                continue

    logger.info(f"Email cleaning completed. Processed {processed} leads.")
    validator.print_stats()

    return validator.stats

# ✅ Main callable function (safe for Django / LangGraph use)
def validate_emails_tool(
    dry_run=False,
    api_validate=False,
    api_key=None,
    batch_size=1000,
    max_workers=4,
    log_level="INFO"
):
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    try:
        logger.info("🚀 Starting email validation...")
        stats = clean_emails(
            dry_run=dry_run,
            use_api=api_validate,
            api_key=api_key,
            batch_size=batch_size,
            max_workers=max_workers
        )

        if dry_run:
            logger.info("\n DRY RUN COMPLETED - No changes were made")
            logger.info("Run without --dry-run to apply changes")
        else:
            logger.info("\n EMAIL CLEANING COMPLETED")
            logger.info(f"Cleaned {stats.cleaned} invalid emails")
            logger.info(f"Corrected {stats.corrected_typos} typos")
            from agent.tools.utils.send_email_update import send_scraping_update
            send_scraping_update(
                subject="✅ EMAIL CLEANING COMPLETED",
                message=f"""Emails verified & validated for outreach.
                            Corrected {stats.corrected_typos} typos.
                            Cleaned {stats.cleaned} invalid emails."""
            )
        return stats

    except KeyboardInterrupt:
        logger.info("\n Process interrupted by user")
        return ValidationStats()
    except Exception as e:
        logger.error(f" Fatal error: {str(e)}")
        raise


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Clean and validate Lead emails')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--api-validate', action='store_true')
    parser.add_argument('--api-key', type=str)
    parser.add_argument('--batch-size', type=int, default=1000)
    parser.add_argument('--max-workers', type=int, default=4)
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])

    args = parser.parse_args()

    validate_emails_tool(
        dry_run=args.dry_run,
        api_validate=args.api_validate,
        api_key=args.api_key,
        batch_size=args.batch_size,
        max_workers=args.max_workers,
        log_level=args.log_level
    )
