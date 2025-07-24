import os
import re
import sys
import time
import random
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path
from django.utils import timezone

import django
from django.core.mail import send_mail, get_connection
from django.conf import settings
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

# Get leads that need follow-up
from django.db.models import Q

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()
from agent.models import Lead


@dataclass
class SMTPConfig:
    """Configuration for SMTP providers"""
    provider: str
    host: str
    port: int
    use_tls: bool
    username: str
    password: str


@dataclass
class MockLead:
    email: str
    username: str
    niche: str
    bio: str = ""
    email_sent: bool = True  # Set to True for follow-up testing
    followup_sent: bool = False
    email_provider_used: str = ""
    last_contacted_at: str = ""

    def save(self):
        """Mock save method for testing"""
        print(f"Mock save: {self.email} - followup_sent: {self.followup_sent}")


test_leads = [
    MockLead(email="michaelogaje033@gmail.com", username="coachmike", niche="fitness",
             bio="Helping people burn fat at home with zero equipment.",
             email_provider_used="test@gmail.com"),
    MockLead(email="kennkiyoshi@gmail.com", username="fitkenn", niche="fitness",
             bio="Helping people build muscle with zero equipment.",
             email_provider_used="test@gmail.com"),
    MockLead(email="owi.09.12.02@gmail.com", username="yogaowi", niche="fitness",
             bio="Helping people build stamina.",
             email_provider_used="test@gmail.com"),
    MockLead(email="unitorial111@gmail.com", username="yogaowi", niche="fitness",
             bio="Helping people select the best nutrition for bodybuilding",
             email_provider_used="test@gmail.com"),
]

class EmailFollowUpManager:
    """Manages follow-up email campaigns with personalized content generation"""

    def __init__(self, openai_api_key: str, smtp_configs: List[SMTPConfig]):
        self.client = OpenAI(api_key=openai_api_key)
        self.smtp_configs = smtp_configs
        self.logger = self._setup_logging()
        self.smtp_index = 0  # 🔄 for round-robin rotation

    def _setup_logging(self) -> logging.Logger:
        """Configure logging with file and console handlers"""
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)

        # Avoid duplicate handlers
        if logger.handlers:
            return logger

        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )

        # File handler
        file_handler = logging.FileHandler('followup_outreach.log')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger

    def generate_followup_email(self, lead, max_retries: int = 3) -> Tuple[Optional[str], Optional[str]]:
        """Generate personalized follow-up email using OpenAI with retry logic"""
        prompt = self.build_followup_email_prompt(lead)

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.9,
                    max_tokens=300
                )

                subject, body = self._parse_email_response(response.choices[0].message.content)

                if subject and body:
                    return subject, body

                self.logger.warning(f"Incomplete response for {lead.email}, attempt {attempt + 1}")

            except Exception as e:
                self.logger.error(f"OpenAI API error for {lead.email}, attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        return None, None

    def build_followup_email_prompt(self, lead) -> str:
        """Build a follow-up email prompt that references the previous outreach"""

        # Extract and validate lead information
        bio_content = lead.bio if lead.bio else getattr(lead, 'business_description', '')
        lead_name = lead.username or "there"
        lead_niche = lead.niche or "your business"

        # Get product information
        from agent.models import Product
        product = Product.objects.get(id=3)

        return f"""
        Instruction:

        You are a skilled copywriter creating a natural, warm follow-up email. This is a second touchpoint to someone who received your first email but hasn't responded yet. The follow-up should feel genuine, helpful, and not pushy.

        **Goal:** Re-engage with value, show persistence without being annoying, and gently encourage a response.

        Use the following details:
        - Lead name: {lead_name}
        - Niche: {lead_niche}
        - Product insight: {product.description}

                
        🎯 Your Goal:
        - Reconnect casually
        - Reference the last email lightly
        - Re-spark interest with one new angle or benefit
        - Keep it warm, helpful, and low-pressure
        
        ---
        
        ✍️ Email Rules:
        - Subject line MUST include their name or username, e.g. “coachmike, this might help”
        - Subject line: lowercase, under 25 words
        - Total word count: under 80 words
        - Do **not** say “just following up” or “checking in”
        - End with a soft CTA like: “want to see?”, “open to a look?”, “should I send more?”

        **Few-shot Examples**

        **Example 1**

        Input:
        {{
          "lead_name": "Maya",
          "lead_niche": "online fitness coaching", 
          "product_input": "AI-powered prompt pack that helps coaches create eye-catching flyers and posters fast"
        }}

        Output:

        Maya, this might make content easier

        Hey Maya,

        Not sure if you saw my last note — been helping other coaches with something that saves hours on design.
        
        Think it could be useful for your setup too.
        
        Want me to send a quick peek?
        
        — Genesis.ai

        ---

        **Example 2**

        Input:
        {{
          "lead_name": "Luis",
          "lead_niche": "wellness and recovery coaching",
          "product_input": "visual content prompts to help coaches design engaging posters in minutes"
        }}

        Output:

       luis, thought you’d like this angle


        Hey luis,

        Quick one — I shared something earlier that might’ve slipped by.
        
        It’s a shortcut for {lead_niche} creators to turn ideas into polished visuals way faster. Been getting solid feedback.
        
        Open to a 10-second look?
        
        — Genesis.ai

        ---

        Now generate a follow-up email using this input:

        Input:
        {{
          "lead_name": "{lead_name}",
          "lead_niche": "{lead_niche}",
          "product_insight": "{product.description}"
        }}

        Expected Output:
        Respond ONLY with the subject line on the first line, followed by a blank line, and then the email body. Do NOT include labels like "Subject:", "Email:", "Body:", or any Markdown formatting.
        """

    def _parse_email_response(self, raw_output: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract subject and body from OpenAI output even if imperfectly formatted."""
        try:
            subject = None
            body = None

            # Handle structured cases (e.g., "SUBJECT: blah", "BODY: blah")
            if "SUBJECT:" in raw_output.upper() and "BODY:" in raw_output.upper():
                subject_match = re.search(r"SUBJECT:\s*(.+)", raw_output, re.IGNORECASE)
                body_match = re.search(r"BODY:\s*(.+)", raw_output, re.IGNORECASE | re.DOTALL)

                subject = subject_match.group(1).strip() if subject_match else None
                body = body_match.group(1).strip() if body_match else None

            else:
                # Fallback: assume first non-empty line is subject, rest is body
                lines = raw_output.strip().splitlines()
                lines = [line.strip() for line in lines if line.strip() != ""]

                if len(lines) >= 2:
                    subject = lines[0]
                    body = "\n".join(lines[1:])
                elif len(lines) == 1:
                    subject = lines[0]
                    body = ""
                else:
                    subject = body = None

            # Clean formatting artifacts (e.g., bullets or asterisks)
            if subject:
                subject = re.sub(r"^[*•\-]+", "", subject).strip()
            if body:
                body = re.sub(r"^[*•\-]+", "", body).strip()

            return subject, body

        except Exception as e:
            self.logger.error(f"Email parse failed: {str(e)}")
            return None, None

    def send_email(self, subject: str, body: str, to_email: str, smtp_config: SMTPConfig) -> bool:
        """Send email using specified SMTP configuration"""
        try:
            connection = get_connection(
                host=smtp_config.host,
                port=smtp_config.port,
                username=smtp_config.username,
                password=smtp_config.password,
                use_tls=smtp_config.use_tls,
                use_ssl=False
            )

            send_mail(
                subject=subject,
                message=body,
                from_email=smtp_config.username,
                recipient_list=[to_email],
                connection=connection,
                fail_silently=False
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    def send_batch_followup(self, niche: str = "fitness coach", batch_size: int = 30,
                            delay_minutes: int = 7, min_days_since_first_email: int = 3) -> Dict[str, Any]:
        """
        Send follow-up emails to leads who received initial emails but haven't had follow-ups

        Args:
            niche: Filter leads by niche
            batch_size: Number of emails to send
            delay_minutes: Minutes to wait between each email
            min_days_since_first_email: Minimum days to wait before sending follow-up

        Returns:
            Dictionary with campaign results
        """
        start_time = datetime.now()
        self.logger.info(f"Starting follow-up batch for niche: {niche}")
        self.logger.info(f"Batch size: {batch_size}, Delay: {delay_minutes} minutes")

        # Calculate the cutoff date for initial emails (only follow up after X days)
        cutoff_date = timezone.now() - timedelta(days=min_days_since_first_email)

        # Get leads that:
        # 1. Have email_sent = True (received initial email)
        # 2. Have followup_sent = False (haven't received follow-up yet)
        # 3. Were contacted at least X days ago
        # 4. Match the niche
        leads = Lead.objects.filter(
            niche=niche,
            email_sent=True,
            followup_sent=False,
            #last_contacted_at__lte=cutoff_date
        )[:batch_size]

        if not leads.exists():
            self.logger.info("No leads found that need follow-up emails.")
            return self._build_summary(0, 0, 0, start_time)

        self.logger.info(f"Found {leads.count()} leads that need follow-up")

        successful_sends = 0
        failed_sends = 0

        # Use tqdm for progress tracking
        for i, lead in enumerate(tqdm(leads, desc="Sending follow-up emails")):
            try:
                result = self._process_single_followup_lead(lead, i, batch_size, delay_minutes)
                if result:
                    successful_sends += 1
                else:
                    failed_sends += 1

            except Exception as e:
                self.logger.error(f"Unexpected error processing {lead.email}: {str(e)}")
                failed_sends += 1

        return self._build_summary(leads.count(), successful_sends, failed_sends, start_time)

    def _process_single_followup_lead(self, lead, index: int, batch_size: int, delay_minutes: int) -> bool:
        """Process a single lead for follow-up email sending"""

        # Use the same email provider that was used for the initial email
        smtp_config = None

        # Find the SMTP config that matches the email provider used
        for config in self.smtp_configs:
            if config.username == lead.email_provider_used:
                smtp_config = config
                break

        # If we can't find the exact provider, fall back to round-robin
        if not smtp_config:
            self.logger.warning(
                f"Original email provider {lead.email_provider_used} not found for {lead.email}, using fallback")
            smtp_config = self.smtp_configs[self.smtp_index % len(self.smtp_configs)]
            self.smtp_index += 1

        self.logger.info(f"Generating follow-up email for {lead.email}...")
        subject, body = self.generate_followup_email(lead)

        if not subject or not body:
            self.logger.error(f"Skipped {lead.email} - Follow-up email generation failed")
            return False

        # Send email
        if self.send_email(subject, body, lead.email, smtp_config):

            # Send test emails to monitor
            seed_emails = ["unitorial111@gmail.com", "michaelogaje033@outlook.com"]
            for seed in seed_emails:
                self.send_email(subject, body, seed, smtp_config)
                print('Test follow-up emails sent...monitor gradually')

            # Mark follow-up as sent
            lead.followup_sent = True
            lead.last_contacted_at = timezone.now()

            # Only call save() if it's a real Django model
            if hasattr(lead, "save"):
                lead.save()

            self.logger.info(f"[{index + 1}/{batch_size}] Follow-up sent to {lead.email} via {smtp_config.provider}")
            self.logger.info(f"Subject: {subject}")

            # Wait before next email (except for the last one)
            if index < batch_size - 1:
                delay_seconds = (delay_minutes or 10) * 60

                self.logger.info(f"Waiting {delay_minutes} minutes before next send...")
                time.sleep(delay_seconds)

            return True

        return False

    def _build_summary(self, total_processed: int, successful: int, failed: int,
                       start_time: datetime) -> Dict[str, Any]:
        """Build and log campaign summary"""
        from agent.tools.utils.send_email_update import send_scraping_update

        end_time = datetime.now()
        duration = end_time - start_time
        subject = "Genesis Follow-up Summary ✅"
        body = (
            f"Follow-up batch finished.\n\n"
            f"Total: {total_processed}\n"
            f"Sent: {successful}\n"
            f"Failed: {failed}\n"
            f"Rate: {(successful / total_processed * 100) if total_processed > 0 else 0}%\n"
            f"Duration: {duration}\n"
        )
        send_scraping_update(subject, body)

        summary = {
            'total_processed': total_processed,
            'successful_sends': successful,
            'failed_sends': failed,
            'duration': duration,
            'start_time': start_time,
            'end_time': end_time,
            'success_rate': (successful / total_processed * 100) if total_processed > 0 else 0
        }

        self.logger.info("=" * 50)
        self.logger.info("FOLLOW-UP OUTREACH SUMMARY")
        self.logger.info("=" * 50)
        self.logger.info(f"Total leads processed: {summary['total_processed']}")
        self.logger.info(f"Successful sends: {summary['successful_sends']}")
        self.logger.info(f"Failed sends: {summary['failed_sends']}")
        self.logger.info(f"Success rate: {summary['success_rate']:.1f}%")
        self.logger.info(f"Duration: {summary['duration']}")
        self.logger.info(f"Completed at: {summary['end_time']}")

        return summary


def setup_django():
    """Setup Django environment"""
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
    sys.path.insert(0, str(PROJECT_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    django.setup()


def load_smtp_configs() -> List[SMTPConfig]:
    """Load SMTP configurations from environment variables"""
    load_dotenv()

    configs = []

    # Zoho configuration
    zoho_email = os.getenv("ZOHO_EMAIL")
    zoho_password = os.getenv("zoho_app_password")
    if zoho_email and zoho_password:
        configs.append(SMTPConfig(
            provider="zoho",
            host="smtp.zoho.com",
            port=587,
            use_tls=True,
            username=zoho_email,
            password=zoho_password
        ))

    # Gmail configuration
    gmail_email = os.getenv("EMAIL_HOST_USER")
    gmail_password = os.getenv("EMAIL_HOST_PASSWORD")
    if gmail_email and gmail_password:
        configs.append(SMTPConfig(
            provider="gmail",
            host="smtp.gmail.com",
            port=587,
            use_tls=True,
            username=gmail_email,
            password=gmail_password
        ))

    gmail_email_2 = os.getenv("GMAIL_EMAIL_2")
    gmail_password_2 = os.getenv("GMAIL_APP_PASSWORD_2")
    if gmail_email_2 and gmail_password_2:
        configs.append(SMTPConfig(
            provider="gmail-2",
            host="smtp.gmail.com",
            port=587,
            use_tls=True,
            username=gmail_email_2,
            password=gmail_password_2
        ))

    # Zoho configurations 1-4
    for i in range(1, 5):
        zoho_email_var = f"zoho_email_{i}"
        zoho_password_var = f"zoho_app_password_{i}"

        zoho_email = os.getenv(zoho_email_var)
        zoho_password = os.getenv(zoho_password_var)

        if zoho_email and zoho_password:
            configs.append(SMTPConfig(
                provider=f"zoho-{i}",
                host="smtp.zoho.com",
                port=587,
                use_tls=True,
                username=zoho_email,
                password=zoho_password
            ))

    if not configs:
        raise ValueError("No SMTP configurations found. Please check your environment variables.")

    return configs


def run_manual_test():
    """Run manual test with mock leads"""
    setup_django()  # Only if you're using Django ORM for product

    smtp_configs = load_smtp_configs()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    email_manager = EmailFollowUpManager(openai_api_key, smtp_configs)

    print("🧪 Starting follow-up email test...")
    print("=" * 50)

    for i, lead in enumerate(test_leads):
        print(f"\n📧 Testing lead {i + 1}/{len(test_leads)}: {lead.email}")
        print(f"   Username: {lead.username}")
        print(f"   Niche: {lead.niche}")
        print(f"   Bio: {lead.bio[:50]}...")

        success = email_manager._process_single_followup_lead(lead, i, len(test_leads), delay_minutes=1)

        if success:
            print(f"   ✅ Follow-up sent to {lead.email}")
            print(f"   📤 Via provider: {lead.email_provider_used}")
        else:
            print(f"   ❌ Failed to send follow-up to {lead.email}")

    print("\n" + "=" * 50)
    print("🏁 Test completed!")


def FollowUpOutreach():
    """Main function to run the follow-up email campaign"""
    try:
        # Setup Django
        setup_django()

        # Load configurations
        smtp_configs = load_smtp_configs()
        openai_api_key = os.getenv('OPENAI_API_KEY')

        if not openai_api_key:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY environment variable.")

        # Initialize email manager
        email_manager = EmailFollowUpManager(openai_api_key, smtp_configs)

        # Run follow-up campaign
        results = email_manager.send_batch_followup(
            niche="fitness coach",
            batch_size=30,
            delay_minutes=10,
            min_days_since_first_email=3  # Wait at least 3 days before follow-up
        )

        return results

    except Exception as e:
        logging.error(f"Follow-up campaign failed: {str(e)}")
        raise


if __name__ == "__main__":
    run_manual_test()