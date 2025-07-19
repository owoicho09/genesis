import csv
import os
import sys
from django.conf import settings

# Django setup
# Django setup (if needed)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
print("✅ PROJECT_ROOT:", PROJECT_ROOT)
print("✅ sys.path[0]:", sys.path[0])
print("✅ core folder exists:", os.path.exists(os.path.join(PROJECT_ROOT, "core")))
print("✅ settings.py exists:", os.path.exists(os.path.join(PROJECT_ROOT, "core", "settings.py")))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
import django
django.setup()
from agent.tools.utils.send_email_update import send_scraping_update

from agent.models import Lead  # replace 'agent' with your actual app name
import csv
import os
from django.conf import settings
from agent.models import Lead


def clean_and_export_leads():
    """
    Clean the database by exporting leads without email to CSV (without duplicates) and removing them.
    """
    # Step 1: Fetch all leads
    all_leads = Lead.objects.all()
    total_leads = all_leads.count()
    print(f"📊 Total leads in database: {total_leads}")

    # Step 2: Filter leads with and without email
    leads_with_email = all_leads.exclude(email__isnull=True).exclude(email__exact="")
    leads_without_email = all_leads.filter(email__isnull=True) | all_leads.filter(email__exact="")

    leads_with_email_count = leads_with_email.count()
    leads_without_email_count = leads_without_email.count()

    print(f"📧 Leads with email: {leads_with_email_count}")
    print(f"❌ Leads without email: {leads_without_email_count}")

    # Step 3: Export leads without email to CSV (avoiding duplicates)
    if leads_without_email_count > 0:
        # Ensure the directory exists
        csv_dir = os.path.join(settings.BASE_DIR, 'csv-json')
        os.makedirs(csv_dir, exist_ok=True)

        csv_path = os.path.join(csv_dir, 'leads_without_email.csv')

        # Step 3a: Load existing leads in CSV (avoid duplicates)
        existing_entries = set()
        if os.path.exists(csv_path):
            with open(csv_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (row['Name'].strip().lower(), row['Website'].strip().lower())
                    existing_entries.add(key)

        # Step 3b: Append new unique leads
        with open(csv_path, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)

            # If file is new, write header
            if os.stat(csv_path).st_size == 0:
                writer.writerow(['Name', 'Website', 'Niche'])

            new_exports = 0
            for lead in leads_without_email:
                username = lead.username.strip().lower() if hasattr(lead, 'username') and lead.username else ''
                source_url = lead.source_url.strip().lower() if hasattr(lead, 'source_url') and lead.source_url else ''
                niche = lead.niche if hasattr(lead, 'niche') else ''

                key = (username, source_url)

                if key not in existing_entries:
                    writer.writerow([username, source_url, niche])
                    existing_entries.add(key)
                    new_exports += 1

        print(f"📄 Exported {new_exports} new leads without email to {csv_path}")

        # Step 4: Delete leads without email
        deleted_count, _ = leads_without_email.delete()
        print(f"🗑️ Deleted {deleted_count} leads without email from the database")
    else:
        print("✅ No leads without email found - nothing to export or delete")

    # Final count
    final_count = Lead.objects.count()
    print(f"✅ {final_count} leads with email retained in database")

    return {
        'total_leads': total_leads,
        'exported_count': new_exports if leads_without_email_count > 0 else 0,
        'deleted_count': leads_without_email_count,
        'retained_count': final_count
    }



def purge_exercisecoach_leads():
    """
    Export and delete leads with source_url containing 'exercisecoach.com'
    """
    bad_leads = Lead.objects.filter(source_url__icontains="exercisecoach.com")
    count = bad_leads.count()

    if count == 0:
        print("✅ No leads from exercisecoach.com found.")
        return

    # Export before deleting
    csv_dir = os.path.join(settings.BASE_DIR, 'csv-json')
    os.makedirs(csv_dir, exist_ok=True)
    csv_path = os.path.join(csv_dir, 'exercisecoach_leads.csv')

    with open(csv_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Name', 'Email', 'Niche', 'Source URL'])

        for lead in bad_leads:
            writer.writerow([
                getattr(lead, 'username', ''),
                getattr(lead, 'email', ''),
                getattr(lead, 'niche', ''),
                getattr(lead, 'source_url', '')
            ])

    deleted, _ = bad_leads.delete()
    print(f"🗑️ Deleted {deleted} leads from exercisecoach.com and exported to {csv_path}")




def cleaner():
    """Main function to run the cleaning process."""
    print("🚀 Starting database cleaning process...")
    print("=" * 60)

    try:
        # First, purge low-quality leads
        purge_exercisecoach_leads()

        result = clean_and_export_leads()
        subject = "Cleaning successful"
        message = f"""✅ Database cleaning completed successfully!
                    Summary: {result['exported_count']} exported,
                    {result['deleted_count']} deleted,
                    {result['retained_count']} retained

            """
        send_scraping_update(subject, message)

        print("=" * 60)
        print("✅ Database cleaning completed successfully!")
        print(
            f"Summary: {result['exported_count']} exported, {result['deleted_count']} deleted, {result['retained_count']} retained")

    except Exception as e:
        print(f"❌ Error during cleaning process: {str(e)}")
        print("Please check your Django settings and database connection.")
        sys.exit(1)


if __name__ == "__main__":
    cleaner()