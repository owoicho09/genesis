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


if __name__ == "__main__":
    export_valid_leads()
