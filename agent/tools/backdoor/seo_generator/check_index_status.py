import requests,os,sys
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from django.conf import settings
from django.core.mail import send_mail



# Point to root (C:\Users\HP\Desktop\genesis.ai)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")


from_email = settings.FROM_EMAIL
to_email = settings.FROM_EMAIL  # Send to yourself if not specified



SITEMAP_URL = "https://owoicho09.github.io/seo-blog/sitemap.xml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}


def send_alert(subject: str, html_message: str):
    """
    Sends an email using Django's SMTP backend configured in settings.py.
    """
    try:

        send_mail(
            subject=subject,
            message="",  # leave plain text blank if sending only HTML
            from_email=from_email,
            recipient_list=[to_email],
            fail_silently=False,
            html_message=html_message,
        )

        return {"status": "sent", "to": to_email, "subject": subject}

    except Exception as e:
        return {"status": "failed", "error": str(e)}







def fetch_sitemap_urls(sitemap_url):
    res = requests.get(sitemap_url, headers=HEADERS)
    urls = []
    print("Status:", res.status_code)
    print("Raw XML:", res.text[:1000])  # print first 1000 chars

    if res.status_code == 200:
        root = ET.fromstring(res.text)
        for url in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url"):
            loc = url.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            if loc is not None:
                urls.append(loc.text)
    return urls

def check_indexed(url):
    search_url = f"https://www.google.com/search?q=site:{url}"
    res = requests.get(search_url, headers=HEADERS)
    if res.status_code != 200:
        print(f"⚠️  Google search failed for {url} — Status code: {res.status_code}")
        return "❌ Failed to check"
    soup = BeautifulSoup(res.text, "html.parser")
    results = soup.select("div#search div.g")
    return "✅ Indexed" if results else "❌ Not Indexed"

def main():
    print("🔍 Fetching sitemap URLs...")
    urls = fetch_sitemap_urls(SITEMAP_URL)
    if not urls:
        print("❌ No URLs found in sitemap.")
        return

    print(f"🔗 {len(urls)} URLs found. Checking indexing status...\n")

    result_lines = []
    for url in urls:
        status = check_indexed(url)

        line = f"{status} — {url}"
        result_lines.append(line)
        print(line)
        time.sleep(240)  # wait 15 seconds to avoid 429
    # Prepare a clean summary of results
    indexed = [r for r in result_lines if r["status"] == "✅ Indexed"]
    not_indexed = [r for r in result_lines if "❌" in r["status"]]

    summary_html = f"""
    <h2>📊 Genesis SEO Indexing Summary</h2>
    <p><strong>Total URLs Checked:</strong> {len(result_lines)}</p>
    <p><strong>✅ Indexed:</strong> {len(indexed)}</p>
    <p><strong>❌ Not Indexed or Failed:</strong> {len(not_indexed)}</p>
    <hr>
    <h3>Not Indexed URLs:</h3>
    <ul>
    {''.join(f"<li>{line}</li>" for line in not_indexed)}
    </ul>
    """

    subject = "📊 Genesis SEO Indexing Report"
    send_alert(subject=subject, html_message=summary_html)


if __name__ == "__main__":
    main()
