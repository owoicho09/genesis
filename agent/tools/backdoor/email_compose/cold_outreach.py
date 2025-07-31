#!/usr/bin/env python3
"""
Cold Outreach Email Generator (GPT-powered)
===========================================
Generates personalized cold emails for leads using GPT.
"""
import os,re
import sys
import time
import random
import logging
from datetime import datetime
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


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")


import django

django.setup()
from agent.models import Lead

# Get unsent leads
from django.db.models import Q


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
    email_sent: bool = False
    email_provider_used: str = ""

test_leads = [
    MockLead(email="michaelogaje033@gmail.com", username="coachmike", niche="fitness",
             bio="Helping people burn fat at home with zero equipment."),
    MockLead(email="kennkiyoshi@gmail.com", username="fitkenn", niche="fitness",
             bio="Helping people build muscle with zero equipment."),
    MockLead(email="owi.09.12.02@gmail.com", username="yogaowi", niche="fitness",
             bio="Helping people build stamina."),
    MockLead(email="unitorial111@gmail.com", username="yogaowi", niche="fitness",
             bio="Helping people select the best nutrition for bodybuilding"),

]


class EmailOutreachManager:
    """Manages email outreach campaigns with personalized content generation"""

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
        file_handler = logging.FileHandler('outreach.log')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger

    def generate_personalized_email(self, lead, max_retries: int = 3) -> Tuple[Optional[str], Optional[str]]:
        """Generate personalized email using OpenAI with retry logic"""
        prompt = self.build_email_prompt(lead)

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

    def build_email_prompt(self, lead) -> str:
        """Build an enhanced prompt for generating professional cold outreach emails"""

        # Extract and validate lead information
        bio_content = lead.bio if lead.bio else getattr(lead, 'business_description', '')
        lead_name = lead.username or "there"
        lead_niche = lead.niche or "your business"

        # Get product information
        from agent.models import Product
        product = Product.objects.get(id=3)

        return f"""
        Instruction:
        
        You’re writing short, friendly cold emails that feel like one person reaching out to another — casual, clear, and to the point. No sales pitch, no pressure — just a quick message that shows you understand their world and might have something useful.
        
        **Goal:** Get their attention fast, show you understand their space, and offer a simple, relevant solution in just a few words.
        
        Use this info:
        - Lead name: {lead_name}
        - Niche: {lead_niche}
        - Product insight: {product.description}
        
        **Tone & Style Rules:**
        - Write like a real person, not a marketer.
        - Keep it short — max 3 sentences, under 70 words.
        - Subject line should be lowercase, simple, and curiosity-driven (max 30 words).
        - First line: Show you know what they do — quick compliment or mention.
        - Second line: Call out a common challenge in their niche.
        - Third line: Suggest a helpful solution based on the product insight — no product names.
        - End with a soft CTA like “Want a quick peek?” or “Would it be useful?”
        - No spammy or salesy language. Keep it light, human, and real.
        
        ---
        
        **Example Input**
        {{
          "lead_name": "Maya",
          "lead_niche": "fitness coaching",
          "product_input": "an AI prompt pack that helps coaches design flyers and posters in minutes"
        }}
        
        **Expected Output**
        create fitness flyers in less time
        
        Hey Maya,
        
        Saw your coaching content — super clean and clear.  
        Most coaches I talk to spend way too long designing flyers or promo posts — been working on a shortcut for that.  
        Might be helpful — want a quick look?
        
        — Genesis.ai
        
        ---
   

        Now generate an email using this input:

        Input:
        {{
          "lead_name": "{lead_name}",
          "lead_niche": "{lead_niche}",
          "product_insight": "{product.description}"
        }}

        Expected Output:
        Respond ONLY with the subject line on the first line, followed by a blank line, and then the email body. Do NOT include labels like "Subject:", "Email:", "Body:", or any Markdown formatting.

        Example format:
        a quick idea for your coaching graphics

        Hey Taylor,

        Been following your content — love how polished your visuals are and how clear your messaging feels.

        I’ve noticed coaches often get stuck spending too much time designing promo materials. I’ve been working on a little shortcut that helps speed that part up — and still keeps it looking sharp.

        Would you be open to a quick look?

        — Genesis.ai
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
            self.logger.error(f" Email parse failed: {str(e)}")
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
                use_ssl=False  # ✅ Force this to False
            )
            #message = body + f'\n\n<img src="https://yourdomain.com/email-open/{to_email}" width="1" height="1" style="display:none;" />'

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

    def send_batch_outreach(self, niche: str = "fitness coach", batch_size: int = 30,
                            delay_minutes: int = 7) -> Dict[str, Any]:
        """
        Send cold outreach emails in batches with controlled timing

        Args:
            niche: Filter leads by niche
            batch_size: Number of emails to send
            delay_minutes: Minutes to wait between each email

        Returns:
            Dictionary with campaign results
        """
        start_time = datetime.now()
        self.logger.info(f"Starting batch outreach for niche: {niche}")
        self.logger.info(f"Batch size: {batch_size}, Delay: {delay_minutes} minutes")

        # Import here to avoid circular imports

        # Get unsent leads with bio or business description
        leads = Lead.objects.filter(
            niche=niche,
            email_sent=False,
        )[:batch_size]

        if not leads.exists():
            self.logger.info(" No unsent leads found.")
            return self._build_summary(0, 0, 0, start_time)

        self.logger.info(f"Found {leads.count()} leads to contact")

        successful_sends = 0
        failed_sends = 0

        # Use tqdm for progress tracking
        for i, lead in enumerate(tqdm(leads, desc="Sending emails")):
            try:
                result = self._process_single_lead(lead, i, batch_size, delay_minutes)
                if result:
                    successful_sends += 1
                else:
                    failed_sends += 1

            except Exception as e:
                self.logger.error(f" Unexpected error processing {lead.email}: {str(e)}")
                failed_sends += 1

        return self._build_summary(leads.count(), successful_sends, failed_sends, start_time)

    def _process_single_lead(self, lead, index: int, batch_size: int, delay_minutes: int) -> bool:
        """Process a single lead for email sending"""
        # Select random SMTP account for better distribution
        smtp_config = self.smtp_configs[self.smtp_index % len(self.smtp_configs)]
        self.smtp_index += 1

        self.logger.info(f"Generating email for {lead.email}...")
        subject, body = self.generate_personalized_email(lead)

        if not subject or not body:
            self.logger.error(f" Skipped {lead.email} - Email generation failed")
            return False

        # Send email
        if self.send_email(subject, body, lead.email, smtp_config):

            seed_emails = ["unitorial111@gmail.com","michaelogaje033@outlook.com"]
            for seed in seed_emails:
                self.send_email(subject, body, seed, smtp_config)
                print('Test emails sent..monitor gradually')

            # Mark as sent
            lead.email_sent = True
            lead.email_provider_used = smtp_config.username
            lead.last_contacted_at = timezone.now()

            # Only call save() if it's a real Django model
            if hasattr(lead, "save"):
                lead.save()

            self.logger.info(f" [{index + 1}/{batch_size}] Sent to {lead.email} via {smtp_config.provider}")
            self.logger.info(f"Subject: {subject}")

            # Wait before next email (except for the last one)
            if index < batch_size - 1:
                delay_seconds = (delay_minutes or 10) * 60  # Convert to seconds

                #delay_seconds = random.randint(600, 900)  # 10–15 minutes

                self.logger.info(f" Waiting {delay_minutes} minutes before next send...")
                time.sleep(delay_seconds)

            return True

        return False

    def _build_summary(self, total_processed: int, successful: int, failed: int,
                       start_time: datetime) -> Dict[str, Any]:
        """Build and log campaign summary"""
        from agent.tools.utils.send_email_update import send_scraping_update

        end_time = datetime.now()
        duration = end_time - start_time
        subject = "Genesis Outreach Summary ✅",
        body = (
            f"Batch finished.\n\n"
            f"Total: {total_processed}\n"
            f"Sent: {successful}\n"
            f"Failed: {failed}\n"
            f"Rate: {(successful / total_processed * 100) if total_processed > 0 else 0}%\n"
            f"Duration: {duration}\n"
        )
        send_scraping_update(subject,body)
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
        self.logger.info("BATCH OUTREACH SUMMARY")
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
    #gmail_email = os.getenv("EMAIL_HOST_USER")
    #gmail_password = os.getenv("EMAIL_HOST_PASSWORD")
    #if gmail_email and gmail_password:
    #    configs.append(SMTPConfig(
    #        provider="gmail",
    #        host="smtp.gmail.com",
     #       port=587,
      #      use_tls=True,
      #      username=gmail_email,
      #      password=gmail_password
      #  ))

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

    # Zoho configuration 1
    zoho_email_1 = os.getenv("zoho_email_1")
    zoho_app_password_1 = os.getenv("zoho_app_password_1")
    if zoho_email_1 and zoho_app_password_1:
        configs.append(SMTPConfig(
            provider="zoho",
            host="smtp.zoho.com",
            port=587,
            use_tls=True,
            username=zoho_email_1,
            password=zoho_app_password_1
        ))

    # Zoho configuration 2 - FIXED: Now checking correct variables
    zoho_email_2 = os.getenv("zoho_email_2")
    zoho_app_password_2 = os.getenv("zoho_app_password_2")
    if zoho_email_2 and zoho_app_password_2:
        configs.append(SMTPConfig(
            provider="zoho",
            host="smtp.zoho.com",
            port=587,
            use_tls=True,
            username=zoho_email_2,
            password=zoho_app_password_2
        ))

    # Zoho configuration 3 - FIXED: Now checking correct variables
    zoho_email_3 = os.getenv("zoho_email_3")
    zoho_app_password_3 = os.getenv("zoho_app_password_3")
    if zoho_email_3 and zoho_app_password_3:
        configs.append(SMTPConfig(
            provider="zoho",
            host="smtp.zoho.com",
            port=587,
            use_tls=True,
            username=zoho_email_3,
            password=zoho_app_password_3
        ))

    # Zoho configuration 4 - FIXED: Now checking correct variables
    zoho_email_4 = os.getenv("zoho_email_4")
    zoho_app_password_4 = os.getenv("zoho_app_password_4")
    if zoho_email_4 and zoho_app_password_4:
        configs.append(SMTPConfig(
            provider="zoho",
            host="smtp.zoho.com",
            port=587,
            use_tls=True,
            username=zoho_email_4,
            password=zoho_app_password_4
        ))



    if not configs:
        raise ValueError("No SMTP configurations found. Please check your environment variables.")

    return configs


def run_manual_test():
    setup_django()  # Only if you're using Django ORM for product

    smtp_configs = load_smtp_configs()
    openai_api_key = os.getenv("OPENAI_API_KEY")
    manager = EmailOutreachManager(openai_api_key, smtp_configs)

    for i, lead in enumerate(test_leads):
        success = manager._process_single_lead(lead, i, len(test_leads), delay_minutes=0)

        if success:
            print(f"✅ Sent to {lead.email} via {lead.email_provider_used}")
        else:
            print(f"❌ Failed to send to {lead.email}")



def main():
    """Main function to run the email outreach campaign"""
    try:
        # Setup Django
        setup_django()

        # Load configurations
        smtp_configs = load_smtp_configs()
        openai_api_key = os.getenv('OPENAI_API_KEY')

        if not openai_api_key:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY environment variable.")

        # Initialize email manager
        email_manager = EmailOutreachManager(openai_api_key, smtp_configs)

        # Run campaign
        results = email_manager.send_batch_outreach(
            niche="fitness coach",
            batch_size=30,
            delay_minutes=10
        )

        return results

    except Exception as e:
        logging.error(f"Campaign failed: {str(e)}")
        raise


if __name__ == "__main__":
    #main()
    run_manual_test()
