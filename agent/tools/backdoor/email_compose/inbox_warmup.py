#!/usr/bin/env python3
"""
Email Warm-Up and Outreach System
==================================
Handles sending warm-up emails using static templates or GPT-generated content.
"""

import os, sys, time, json, random, logging
from datetime import datetime
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

import django
from django.utils import timezone
from django.core.mail import send_mail, get_connection

# ---- Django Setup ----
def setup_django():
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
    sys.path.insert(0, PROJECT_ROOT)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    django.setup()


# ---- Config ----
WARMUP_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "warmup_templates.json")
USE_GPT = False  # 🔄 Set to True if using GPT for real outreach
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))

sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

STATE_FILE_PATH = os.path.join(os.path.dirname(__file__), "warmup_state.json")

def load_last_index() -> int:
    if not os.path.exists(STATE_FILE_PATH):
        return -1
    try:
        with open(STATE_FILE_PATH, "w", encoding="utf-8") as f:
            return json.dump({"last_index": index}, f)
    except Exception:
        return -1

def save_last_index(index: int):
    with open(STATE_FILE_PATH, "w") as f:
        json.dump({"last_index": index}, f)

def clear_warmup_state():
    """Delete the warmup state file to reset the cycle"""
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)


from agent.tools.utils.send_email_update import send_scraping_update

# ---- SMTP Configuration ----
@dataclass
class SMTPConfig:
    provider: str
    host: str
    port: int
    use_tls: bool
    username: str
    password: str


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

# ---- Email Manager ----
class EmailWarmUpManager:

    def __init__(self, smtp_configs: List[SMTPConfig]):
        self.smtp_configs = smtp_configs
        self.smtp_index = 0
        self.logger = self._setup_logging()
        self.templates = self._load_warmup_templates()

    def _setup_logging(self):
        logger = logging.getLogger(__name__)
        if logger.handlers:
            return logger

        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        fh = logging.FileHandler('warmup.log')
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        return logger

    def _load_warmup_templates(self) -> List[Dict[str, str]]:
        """Load warmup templates from JSON file, create default if not found"""
        try:
            with open(WARMUP_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.warning(f"Template file {WARMUP_TEMPLATE_PATH} not found. Creating default templates.")
            return self._create_default_templates()

    def _create_default_templates(self) -> List[Dict[str, str]]:
        """Create default warmup email templates"""
        default_templates = [
            {
                "subject": "Quick question about your fitness journey",
                "body": "Hi there!\n\nI've been following your fitness content and I'm really impressed with your approach. I had a quick question about your training methodology - would you be open to a brief chat?\n\nBest regards"
            },
            {
                "subject": "Loved your recent fitness post",
                "body": "Hello!\n\nI just saw your recent post about fitness training and found it really insightful. I'm working on something similar and would love to connect.\n\nLooking forward to hearing from you!"
            },
            {
                "subject": "Collaboration opportunity",
                "body": "Hi!\n\nI hope this message finds you well. I'm reaching out because I believe we might have some interesting collaboration opportunities in the fitness space.\n\nWould you be interested in a quick call to discuss?\n\nBest"
            }
        ]

        # Save default templates to file
        try:
            with open(WARMUP_TEMPLATE_PATH, "w") as f:
                json.dump(default_templates, f, indent=2)
            self.logger.info(f"Created default template file at {WARMUP_TEMPLATE_PATH}")
        except Exception as e:
            self.logger.error(f"Failed to create template file: {e}")

        return default_templates

    def _get_next_smtp(self) -> SMTPConfig:
        smtp = self.smtp_configs[self.smtp_index % len(self.smtp_configs)]
        self.smtp_index += 1
        return smtp

    def _get_random_warmup_email(self) -> Tuple[str, str]:
        selected = random.choice(self.templates)
        return selected["subject"], selected["body"]

    def send_email(self, subject: str, body: str, to_email: str, smtp_config: SMTPConfig) -> bool:
        try:
            connection = get_connection(
                host=smtp_config.host,
                port=smtp_config.port,
                username=smtp_config.username,
                password=smtp_config.password,
                use_tls=smtp_config.use_tls,
                use_ssl=False
            )
            tracking_pixel = f'<div style="display:none;"><img src="https://yourdomain.com/email-open/{to_email}" width="1" height="1" /></div>'
            html_message = body.replace("\n", "<br>\n") + tracking_pixel

            send_mail(
                subject=subject,
                message=body,
                from_email=smtp_config.username,
                recipient_list=[to_email],
                connection=connection,
                fail_silently=False,
                html_message=html_message  # 👈 This renders as HTML

            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    def send_warmup_batch(self, leads: List, leads_per_inbox: int = 2, delay_minutes: int = 1):
        total_leads = len(leads)
        total_inboxes = len(self.smtp_configs)
        total_to_send = total_inboxes * leads_per_inbox

        last_index = load_last_index()
        next_index = (last_index + 1) % total_leads

        selected_leads = []

        for i in range(total_to_send):
            index = (next_index + i) % total_leads
            selected_leads.append(leads[index])

        for i, lead in enumerate(tqdm(selected_leads, desc="Sending warmup batch")):
            smtp = self._get_next_smtp()
            subject, body = self._get_random_warmup_email()

            if not subject or not body:
                self.logger.error(f"Skipping {lead.email} - No template.")
                continue

            sent = self.send_email(subject, body, lead.email, smtp)

            if sent:
                self.logger.info(f"[{i + 1}] Sent to {lead.email} via {smtp.username}")
            else:
                self.logger.warning(f"[{i + 1}] Failed to send to {lead.email}")

            if i < len(selected_leads) - 1:
                time.sleep(delay_minutes * 60)

        # Update index
        new_index = (next_index + total_to_send - 1) % total_leads
        if new_index == total_leads - 1:
            self.logger.info("✅ Full cycle complete. Resetting warmup state.")
            clear_warmup_state()
        else:
            save_last_index(new_index)

        subject = "Genesis inbox warm-up Completed ✅",
        body = (
            f"A total of {total_to_send} emails were sent"
        )
        send_scraping_update(subject, body)


# ---- Mock Leads for Warmup Test ----
@dataclass
class MockLead:
    email: str
    username: str
    niche: str
    bio: str = ""

test_leads = [
    MockLead(email="michaelogaje033@gmail.com", username="coachmike", niche="fitness"),
    MockLead(email="kennkiyoshi@gmail.com", username="fitkenn", niche="fitness"),
    MockLead(email="owi.09.12.02@gmail.com", username="yogaowi", niche="fitness"),
    MockLead(email="unitorial111@gmail.com", username="traineruni", niche="fitness"),
    MockLead(email="michaelogaje033@hotmail.com", username="coachmike", niche="fitness"),
    MockLead(email="michaelogaje033@outlook.com", username="coachmike", niche="fitness"),
    MockLead(email="owi0912@hotmail.com", username="owi", niche="fitness"),
    MockLead(email="owi0912@outlook.com", username="owi", niche="fitness"),
    MockLead(email="009.012.k2@gmail.com", username="k2", niche="fitness"),
    MockLead(email="genesis.ai1@hotmail.com", username="genesisai", niche="fitness"),
    MockLead(email="genesis.aii@hotmail.com", username="genesisai", niche="fitness"),
    MockLead(email="genesis.aii@proton.me", username="genesisai", niche="fitness"),
    MockLead(email="michaelogaje033@proton.me", username="coachmike", niche="fitness"),
    MockLead(email="kacheowoicho@yahoo.com", username="kache", niche="fitness"),
    MockLead(email="michael.m1904722@st.futminna.edu.ng", username="michael", niche="fitness"),
    MockLead(email="ogajemougt5117@st.futminna.edu.ng", username="ogaje", niche="fitness"),
    MockLead(email="u15529464@gmail.com", username="studentfit", niche="fitness"),
]


# ---- Utility Functions ----
def validate_email_format(email: str) -> bool:
    """Basic email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def filter_valid_leads(leads):
    """Filter out leads with invalid email formats"""
    valid_leads = []
    for lead in leads:
        if validate_email_format(lead.email):
            valid_leads.append(lead)
        else:
            print(f"Warning: Invalid email format for {lead.email}")
    return valid_leads




# ---- Run Warmup ----
def run_warmup():
    """Main function to run the warmup process"""
    setup_django()

    try:
        smtp_configs = load_smtp_configs()
        manager = EmailWarmUpManager(smtp_configs)

        # Filter valid leads
        valid_leads = filter_valid_leads(test_leads)

        if not valid_leads:
            print("No valid leads found. Please check your test data.")
            return

        print(f"Starting warmup for {len(valid_leads)} leads...")
        manager.send_warmup_batch(valid_leads, leads_per_inbox=2, delay_minutes=1)
        print("Warmup process completed!")

    except Exception as e:
        print(f"Error during warmup: {e}")


if __name__ == "__main__":
    run_warmup()