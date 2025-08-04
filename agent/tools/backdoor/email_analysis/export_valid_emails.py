#!/usr/bin/env python3
"""
Export Valid Leads to CSV
=========================

Exports all valid (non-null) leads with emails from the database to a CSV file.
"""

import csv
import os
import sys
import django
import datetime

import os
import django
import sys
import csv
from django.core.mail import EmailMessage
from django.conf import settings
from difflib import SequenceMatcher

# Setup Django

# Set up Django environment
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

django.setup()

from agent.models import Lead


EXPORT_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "valid_leads_export.csv"))

FIELDS = ["id", "email", "username", "source_url", "niche", "created_at"]


def export_valid_leads():
    seen_emails = set()

    # Load already-exported emails if the file exists
    if os.path.exists(EXPORT_FILE):
        with open(EXPORT_FILE, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                email = row.get("email", "").strip().lower()
                if email:
                    seen_emails.add(email)

    leads = Lead.objects.filter(email__isnull=False).exclude(email="").order_by('-created_at')

    if not leads.exists():
        print("❌ No valid leads found with emails.")
        return

    # Use append mode if file already exists
    file_mode = 'a' if os.path.exists(EXPORT_FILE) else 'w'

    with open(EXPORT_FILE, mode=file_mode, newline='', encoding='utf-8') as file:
        writer = csv.writer(file)

        # Write header only if creating a new file
        if file_mode == 'w':
            writer.writerow(FIELDS)

        count = 0
        for lead in leads:
            email = lead.email.strip().lower()
            if email in seen_emails:
                continue  # Skip already-exported email

            seen_emails.add(email)
            writer.writerow([
                lead.id,
                lead.email,
                getattr(lead, "username", ""),
                getattr(lead, "source_url", ""),
                getattr(lead, "niche", ""),
                lead.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(lead, "created_at") else "",
            ])
            count += 1

    print(f"✅ Exported {count} new unique leads to '{EXPORT_FILE}'.")



def get_closest_niche(query):
    all_niches = Lead.objects.exclude(niche=None).values_list('niche', flat=True).distinct()
    best_match = max(all_niches, key=lambda n: SequenceMatcher(None, n.lower(), query.lower()).ratio())
    return best_match


def export_leads_to_csv(niche, file_path):
    leads = Lead.objects.filter(niche__icontains=niche)
    if not leads.exists():
        print(f"❌ No leads found for niche similar to '{niche}'")
        return None

    with open(file_path, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Name', 'Email', 'Phone', 'Address', 'Niche', 'Website'])

        for lead in leads:
            writer.writerow([
                lead.username,
                lead.email,
                lead.phone or '',
                lead.address or '',
                lead.niche,
                lead.source_url or ''
            ])

    print(f"✅ Exported {leads.count()} leads to: {file_path}")
    return file_path


def email_csv(file_path, niche):
    subject = f"🎯 Exported Leads - {niche}"
    body = f"Attached are the exported leads for the niche '{niche}'."
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = ['michaelogaje033@gmail.com']

    email = EmailMessage(subject, body, from_email, to_email)
    email.attach_file(file_path)
    email.send()
    print("📧 Email sent successfully to", to_email[0])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python export_valid_emails.py <niche>")
        sys.exit(1)

    input_niche = sys.argv[1]
    print(f"\n🔍 Matching niche for: '{input_niche}'")

    actual_niche = get_closest_niche(input_niche)
    print(f"👉 Using closest match: '{actual_niche}'")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"leads_{actual_niche.replace(' ', '_')}_{timestamp}.csv"
    file_path = os.path.join(os.path.dirname(__file__), filename)

    exported = export_leads_to_csv(actual_niche, file_path)
    if exported:
        email_csv(file_path, actual_niche)
        print("✅ Done!\n")
    else:
        print("🚫 Nothing exported.\n")



#if __name__ == "__main__":
 #   export_valid_leads()
