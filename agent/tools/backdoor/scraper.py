import os
import sys
import traceback

# Setup Django
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django
django.setup()

# Scraper Tool Imports
from agent.tools.backdoor.email_fetcher.google_map import google_map
from agent.tools.backdoor.email_fetcher.insta_scrape import run_instagram_dork_scraper
from agent.tools.backdoor.email_fetcher.ig_sweep import run_ig_sweep_scraper
from agent.tools.backdoor.email_fetcher.map_url_extractor import run_email_extractor
from agent.tools.backdoor.email_fetcher.email_extractor import extract_business_info_tool
from agent.tools.backdoor.email_analysis.verify_email import validate_emails_tool
from agent.tools.backdoor.email_analysis.export_valid_emails import export_valid_leads
from agent.tools.utils.cleaner import cleaner




def google_map_scraping(niche: str, location:str) -> str:
    try:
        print(f"🌍 Starting Google Map scraping for niche: {niche} in {location}")
        output_path = google_map(niche,location)

        csv_file = f"csv-json/{niche.replace(' ', '_')}.csv"
        run_email_extractor(output_path, validate=False, verbose=False)

        extract_business_info_tool()
        cleaner()
        validate_emails_tool()
        export_valid_leads()

        return f"✅ Google Maps scraping & processing complete for: {niche}"
    except Exception as e:
        error_trace = traceback.format_exc()
        return f"❌ Google Maps scraping failed for: {niche}\nError: {str(e)}\n{error_trace}"


def instagram_scraping(niche: str) -> str:
    try:
        print(f"📸 Starting Instagram scraping for niche: {niche}")
        run_instagram_dork_scraper(niches=[niche], max_profiles=50)
        run_ig_sweep_scraper()
        extract_business_info_tool()
        validate_emails_tool()
        export_valid_leads()

        return f"✅ Instagram scraping & processing complete for: {niche}"
    except Exception as e:
        error_trace = traceback.format_exc()
        return f"❌ Instagram scraping failed for: {niche}\nError: {str(e)}\n{error_trace}"


if __name__ == "__main__":
    niche_google = "fitness coach in arizona"
    niche_instagram = "fitness"

    google_response = google_map_scraping(niche_google)
    print(google_response)

    instagram_response = instagram_scraping(niche_instagram)
    print(instagram_response)
