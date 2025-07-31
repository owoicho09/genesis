import os
import sys

# Get the absolute path to the root of your Django project
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))  # only go up 2 levels
#print("PROJECT_ROOT =", PROJECT_ROOT)
#print("Contents of PROJECT_ROOT =", os.listdir(PROJECT_ROOT))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

#print("PYTHONPATH =", sys.path)


# Tell Django where to find settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Set up Django
import django
django.setup()


from agent.models import Lead

# --- STEP 1: Clear all leads with "Uncategorized" to empty string ---
Lead.objects.filter(niche__iexact="Uncategorized").update(niche="")


# --- STEP 2: Improved categorization logic ---
def categorize_lead(lead):
    text = f"{lead.username or ''} {lead.niche or ''} {lead.business_description or ''} {lead.bio or ''} {lead.source_name or ''} {lead.source_url or ''}".lower()

    if any(kw in text for kw in ["fitness", "gym", "coach", "trainer", "wellness"]):
        return "Fitness"
    elif any(kw in text for kw in ["real estate", "realestate", "property", "realtor", "agent", "housing"]):
        return "Real Estate"
    elif any(kw in text for kw in ["marketing", "seo", "branding", "advertising", "growth"]):
        return "Marketing"
    elif any(kw in text for kw in ["law", "legal", "lawyer", "attorney"]):
        return "Legal"
    elif any(kw in text for kw in ["school", "tutor", "teacher", "education", "university"]):
        return "Education"
    else:
        return ""  # Still uncategorized


# --- STEP 3: Re-categorize all leads with blank or null niche ---
def main():
    leads = Lead.objects.filter(niche__isnull=True) | Lead.objects.filter(niche="")
    count = 0

    for lead in leads:
        new_niche = categorize_lead(lead)
        if new_niche:
            lead.niche = new_niche
            lead.save()
            count += 1

    print(f"✅ Updated {count} leads with new niche categories.")
    remaining = Lead.objects.filter(niche="")
    print(f"❗ {remaining.count()} leads still uncategorized.")
    for r in remaining[:10]:  # Show first 10
        print(r.username, r.source_url)


if __name__ == "__main__":
    main()