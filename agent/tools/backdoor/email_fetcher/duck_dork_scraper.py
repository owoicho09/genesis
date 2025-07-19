# duck_dork_scraper.py
import os, sys, re, time, csv, json, random, requests
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote, urlparse
from playwright.sync_api import sync_playwright
from django.db import IntegrityError

# Setup Django
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
import django
django.setup()

from agent.models import Lead
PREMIUM_SITES = [
    "linktr.ee", "beacons.ai",
    "instagram.com"
]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/537.36 Chrome/113.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/114.0.5735.110 Safari/537.36"
]


# 🔁 You can expand this list for more niche variations
NICHE_SYNONYMS = {
    'fitness coach': ['fitness trainer', 'personal trainer', 'online coach', 'wellness coach'],
    'yoga': ['yoga instructor', 'yoga coach', 'yoga trainer'],
    'nutritionist': ['dietician', 'nutrition coach', 'health coach'],
    'business coach': ['startup mentor', 'entrepreneur coach', 'executive coach'],
    'life coach': ['personal development coach', 'self improvement mentor'],
}

QUERY_TEMPLATES = [
    '"{niche}" site:{site}',
]



STATE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "bing_state.json"))
SEEN_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "seen_urls.json"))
PROXY_LIST = [None]
BLOCKED_DOMAINS = {
    # Original domains
    "facebook.com", "youtube.com", "tiktok.com", "twitter.com",
    "instagram.com", "pinterest.com", "snapchat.com", "discord.com",

    # Gaming sites (major addition needed)
    "poki.com", "miniclip.com", "addictinggames.com", "kongregate.com",
    "newgrounds.com", "armor.games", "coolmathgames.com", "friv.com",
    "kizi.com", "y8.com", "agame.com", "gameforge.com", "steam.com",
    "epic.games", "origin.com", "ubisoft.com", "ea.com", "activision.com",

    # Entertainment/Media
    "netflix.com", "hulu.com", "twitch.tv", "vimeo.com", "spotify.com",
    "pandora.com", "soundcloud.com", "bandcamp.com",

    # Shopping (less relevant for B2B outreach)
    "amazon.com", "ebay.com", "aliexpress.com", "alibaba.com",
    "walmart.com", "target.com", "bestbuy.com", "costco.com",

    # News/Media (usually not good for coach outreach)
    "cnn.com", "bbc.com", "reuters.com", "forbes.com", "techcrunch.com",
    "buzzfeed.com", "huffpost.com", "theguardian.com", "nytimes.com",

    # Reference/Wiki
    "wikipedia.org", "wikihow.com", "fandom.com", "imdb.com",

    # Adult content indicators
    "xxx", "porn", "sex", "adult", "cam", "escort"
}

# Enhanced junk patterns
JUNK_EMAIL_PATTERNS = [
    r"noreply", r"no-reply", r"donotreply", r"do-not-reply",
    r"support@", r"info@", r"admin@", r"webmaster@", r"postmaster@",
    r"abuse@", r"security@", r"privacy@", r"legal@", r"billing@",
    r"sales@", r"marketing@", r"pr@", r"press@", r"media@",
    r".*@wixpress\.com", r".*@email\..*", r".*@mail\.ru",
    r".*@example\.com", r".*@test\..*", r".*@localhost",
    r".*@png", r".*@jpg", r".*@gif", r".*@pdf",
    r"test@", r"demo@", r"sample@", r"fake@", r"spam@",
    # Gaming/entertainment specific
    r".*@poki\.com", r".*@miniclip\.com", r".*@addictinggames\.com"
]

EMAIL_REGEX = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"


def is_irrelevant_for_outreach(url, domain):
    """Filter out URLs that are unlikely to contain useful contact information"""

    # Domains to skip for email outreach
    SKIP_DOMAINS = {
        # Social media & forums
        'reddit.com', 'quora.com', 'stackexchange.com', 'stackoverflow.com',
        'github.com', 'gitlab.com', 'bitbucket.com',

        # Job boards & career sites
        'indeed.com', 'glassdoor.com', 'linkedin.com', 'monster.com',
        'ziprecruiter.com', 'careerbuilder.com',

        # Marketplaces & reviews
        'amazon.com', 'ebay.com', 'etsy.com', 'shopify.com',
        'yelp.com', 'tripadvisor.com', 'trustpilot.com',

        # News & media
        'cnn.com', 'bbc.com', 'reuters.com', 'techcrunch.com',
        'forbes.com', 'bloomberg.com', 'wsj.com',

        # Wikis & reference
        'wikipedia.org', 'fandom.com', 'wikia.com',

        # File sharing & docs
        'dropbox.com', 'drive.google.com', 'onedrive.com',
        'docs.google.com', 'scribd.com', 'slideshare.net',

        # App stores
        'play.google.com', 'apps.apple.com', 'microsoft.com/store',
        'chrome.google.com/webstore',

        # Government & edu (often not good for B2B outreach)
        'gov', 'edu', 'mil', 'org'
    }
    # Gaming domains (this was missing!)
    GAMING_DOMAINS = {
        'poki.com', 'miniclip.com', 'addictinggames.com', 'kongregate.com',
        'newgrounds.com', 'armor.games', 'coolmathgames.com', 'friv.com',
        'kizi.com', 'y8.com', 'agame.com', 'steam.com', 'epic.games'
    }
    # Entertainment domains
    ENTERTAINMENT_DOMAINS = {
        'netflix.com', 'hulu.com', 'twitch.tv', 'spotify.com',
        'pandora.com', 'soundcloud.com', 'bandcamp.com'
    }

    # Check domain
    if any(skip_domain in domain for skip_domain in SKIP_DOMAINS):
        return True

    if any(gaming_domain in domain for gaming_domain in GAMING_DOMAINS):
        print(f"🚫 Gaming domain filtered: {domain}")
        return True

    if any(ent_domain in domain for ent_domain in ENTERTAINMENT_DOMAINS):
        print(f"🚫 Entertainment domain filtered: {domain}")
        return True
    # URL path patterns to avoid
    SKIP_PATTERNS = [
        '/games/', '/game/', '/play/', '/online-games/', '/free-games/',
        '/gaming/', '/arcade/', '/puzzle/', '/action/', '/adventure/',
        '/share/', '/social/', '/follow/', '/like/',
        '/profile/', '/user/', '/account/', '/login/', '/register/',
        '/jobs/', '/careers/', '/hiring/', '/job/', '/career/',
        '/blog/', '/news/', '/press/', '/media/',
        '/help/', '/support/', '/faq/', '/documentation/',
        '/privacy/', '/terms/', '/legal/', '/policy/',
        '.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif'
    ]

    url_lower = url.lower()
    if any(pattern in url_lower for pattern in SKIP_PATTERNS):
        return True

    # Prefer pages that might have contact info
    # Fitness-specific preferences
    FITNESS_PATTERNS = [
        '/contact/', '/about/', '/team/', '/trainer/', '/coach/',
        '/services/', '/programs/', '/training/', '/fitness/',
        '/health/', '/wellness/', '/nutrition/', '/workout/',
        '/personal-training/', '/online-coaching/', '/transformation/'
    ]

    # Don't filter URLs that might be fitness-related
    if any(pattern in url_lower for pattern in FITNESS_PATTERNS):
        return False

    return False


# Enhanced blocked domains for email outreach




def load_json(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def bing_search(query, max_results=100):
    offsets = load_json(STATE_FILE)
    seen_urls = load_json(SEEN_FILE)
    offset = offsets.get(query, 0)
    print(f"\n📌 Bing offset for query: {offset}")

    links, seen = [], set()

    # Force region and language to English US
    region_lang = "&mkt=en-US&setlang=en-US"

    for start in range(offset, offset + max_results, 10):
        url = f"https://www.bing.com/search?q={quote(query)}&first={start}{region_lang}"
        print(f"🔍 Bing: {url}")
        try:
            res = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.select("li.b_algo a[href]"):
                href = a.get('href')

                if 'bing.com/ck/a' in href:
                    m = re.search(r'u=(.*?)&', href)
                    if m:
                        href = unquote(m.group(1))
                if href and href.startswith("http"):
                    domain = urlparse(href).netloc

                    if any(b in domain for b in BLOCKED_DOMAINS):
                        continue
                    # Skip irrelevant URLs for email outreach
                    if is_irrelevant_for_outreach(href, domain):
                        continue

                    if href not in seen_urls and href not in seen:
                        links.append(href)
                        seen.add(href)
        except Exception as e:
            print(f"❌ Bing fetch error: {e}")
        time.sleep(random.uniform(1.5, 3))

    offsets[query] = offset + max_results
    save_json(STATE_FILE, offsets)
    print(f"🔗 Fetched new URLs: {len(links)}")
    return links

def is_valid_email(email):
    if not re.match(EMAIL_REGEX, email):
        print(f"❌ Invalid format: {email}")
        return False

    # Check for file extensions (major issue in your case)
    if any(email.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.doc', '.docx']):
        print(f"🚫 File extension detected: {email}")
        return False

    # Check for image/media patterns
    if re.search(r'@\d+x\.|@2x\.|@3x\.', email, re.IGNORECASE):
        print(f"🚫 Image filename pattern: {email}")
        return False

    for p in JUNK_EMAIL_PATTERNS:
        if re.search(p, email, re.IGNORECASE):
            print(f"🚫 Junk pattern matched: {email} | Pattern: {p}")
            return False

    # Domain validation
    domain = email.split('@')[1].lower()
    if any(blocked in domain for blocked in BLOCKED_DOMAINS):
        print(f"🚫 Blocked domain: {email}")
        return False

    return True

def extract_emails_from_url(url):
    emails, visited = set(), set()
    short_description = ""
    company_name = ""

    proxy = random.choice(PROXY_LIST)
    print('♈Extraction in progress')
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(proxy={"server": proxy} if proxy else None)
            page = context.new_page()

            try:
                page.goto(url, timeout=20000, wait_until="networkidle")
                page.wait_for_timeout(2000)
            except:
                try:
                    page.goto(url, timeout=15000, wait_until="domcontentloaded")
                except Exception as e:
                    print(f"⚠️ Failed to load: {url} — {e}")
                    browser.close()
                    return [], "", ""

            print(f"🌍 Extracting from: {url}")
            content = page.content()
            emails.update(re.findall(EMAIL_REGEX, content))

            # Extract company name from title or domain
            try:
                title = page.title()
                if title:
                    company_name = title.split(' | ')[0].split(' - ')[0].strip()[:100]
                else:
                    domain = url.split('/')[2].replace('www.', '')
                    company_name = domain.split('.')[0].title()
            except:
                company_name = ""

            # Enhanced description extraction
            short_description = extract_description(page)

            anchors = page.query_selector_all('a')
            print(f"🔎 Found {len(anchors)} anchor tags")

            for anchor in anchors:
                href = anchor.get_attribute("href") or ""
                label = (anchor.get_attribute("aria-label") or
                         anchor.get_attribute("title") or
                         anchor.inner_text() or "").strip()
                print(f"➡️ Checking link: {href} | Label: {label}")

                # Handle mailto directly
                if href.startswith("mailto:"):
                    email = href.replace("mailto:", "").strip()
                    if is_valid_email(email):
                        print(f"📥 Found mailto: {email}")
                        emails.add(email)
                    continue

                # Fallback regex extraction on href
                if any(domain in href for domain in PREMIUM_SITES + [".com", ".net", ".co"]):
                    possible = re.findall(EMAIL_REGEX, href)
                    for e in possible:
                        if is_valid_email(e):
                            print(f"📥 Found in href: {e}")
                            emails.add(e)

                # Go deeper into external link if it's safe
                if href.startswith("http") and href not in visited and not href.startswith("mailto:"):
                    visited.add(href)
                    try:
                        new_page = context.new_page()
                        new_page.goto(href, timeout=10000, wait_until="domcontentloaded")
                        new_page.wait_for_timeout(1000)
                        sub_content = new_page.content()
                        found = re.findall(EMAIL_REGEX, sub_content)
                        for e in found:
                            if is_valid_email(e):
                                print(f"📥 Found in subpage: {e}")
                                emails.add(e)

                        # mailto inside subpage
                        mailto_anchors = new_page.query_selector_all('a[href^="mailto:"]')
                        for ma in mailto_anchors:
                            m_href = ma.get_attribute("href")
                            if m_href:
                                m_email = m_href.replace("mailto:", "").strip()
                                if is_valid_email(m_email):
                                    print(f"📥 Found mailto in subpage: {m_email}")
                                    emails.add(m_email)
                        new_page.close()
                    except Exception as e:
                        print(f"⚠️ Failed to load external link: {href} — {e}")

            browser.close()

    except Exception as e:
        print(f"⚠️ Outer error while processing: {url} — {e}")
        return [], "", ""

    valid_emails = list(filter(is_valid_email, emails))
    print(f"✅ Emails found: {valid_emails}")
    print(f"🏢 Company: {company_name}")
    print(f"📝 Description: {short_description}")

    return valid_emails, short_description, company_name


def extract_description(page):
    """Extract the best descriptive text from the page"""

    descriptions = []

    # Priority order for description sources

    selectors = [

        'meta[name="description"]',

        'meta[property="og:description"]',

        'meta[name="twitter:description"]',

        '.hero-text, .hero-content, .banner-text',

        'h1 + p, h2 + p',

        '.about-text, .description, .intro',

        'p'

    ]

    for selector in selectors:

        try:

            if selector.startswith('meta'):

                elements = page.query_selector_all(selector)

                for elem in elements:

                    content = elem.get_attribute('content')

                    if content and len(content.strip()) > 30:
                        fitness_keywords = ['fitness', 'training', 'coach', 'health', 'wellness', 'nutrition', 'workout', 'exercise']
                        if any(keyword in content.lower() for keyword in fitness_keywords):
                            descriptions.append(content.strip())

            else:
                elements = page.query_selector_all(selector)
                for elem in elements:
                    text = elem.inner_text().strip()
                    if text and len(text) > 30:
                        fitness_keywords = ['fitness', 'training', 'coach', 'health', 'wellness', 'nutrition',
                                            'workout', 'exercise']
                        if any(keyword in text.lower() for keyword in fitness_keywords):
                            descriptions.append(text)
        except:
            continue

    # If no good description found, extract from body text

    if not descriptions:
        try:
            text = page.inner_text("body").strip()
            lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 50]
            if lines:
                descriptions.append(lines[0])
        except:
            pass

    # Clean and return best description

    if descriptions:
        best_desc = descriptions[0]
        # Clean up the description
        best_desc = re.sub(r'\s+', ' ', best_desc)  # Remove extra whitespace
        best_desc = best_desc.replace('\n', ' ').replace('\t', ' ')
        return best_desc[:300]  # Limit to 300 chars
    return ""


def save_lead(email, url, niche):
    try:
        Lead.objects.create(
            username=email.split('@')[0],
            email=email,
            niche=niche,
            source_url=url,
            status='scraped'
        )
        return True
    except IntegrityError:
        print(f"❌ Duplicate in DB: {email}")
    except Exception as e:
        print(f"❌ Save error: {e}")
    return False

def expand_niches(niches):
    expanded = set()
    for niche in niches:
        expanded.add(niche)
        for alt in NICHE_SYNONYMS.get(niche.lower(), []):
            expanded.add(alt)
    return list(expanded)



def run_scraper(niches, limit=50, export=None):
    """Enhanced scraper that captures emails with descriptive context"""
    all_leads = []
    seen_emails = set()
    seen_urls = load_json(SEEN_FILE)
    failed_urls = set()

    expanded_niches = expand_niches(niches)

    for niche in expanded_niches:
        print(f"\n🚀 Starting scrape for niche: {niche}")
        queries = [
            template.format(niche=niche, site=site)
            for site in PREMIUM_SITES
            for template in QUERY_TEMPLATES
        ]
        random.shuffle(queries)

        for query in queries:
            urls = bing_search(query, max_results=100)

            for url in urls:
                if url in seen_urls:
                    print(f"🟡 Already seen: {url}")
                    continue
                seen_urls[url] = 1

                print(f"\n🌐 Visiting: {url}")
                # Updated to handle the new return format
                emails, description, company_name = extract_emails_from_url(url)
                print(f"📧 Found emails: {emails}")

                if not emails:
                    failed_urls.add(url)
                    continue

                for email in emails:
                    email = email.lower()
                    if email in seen_emails:
                        continue
                    print(f"📥 Saving: {email}")

                    # Enhanced save_lead function call with description
                    if save_lead_with_context(email, url, niche, description, company_name):
                        print('✅ Email saved to DB.')
                        seen_emails.add(email)
                        all_leads.append({
                            'username': email.split('@')[0],
                            'email': email,
                            'niche': niche,
                            'source_url': url,
                            'description': description,
                            'company_name': company_name
                        })
                    if len(all_leads) >= limit:
                        break
                if len(all_leads) >= limit:
                    break
            if len(all_leads) >= limit:
                break

    save_json(SEEN_FILE, seen_urls)

    if export and all_leads:
        with open(export, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'username', 'email', 'niche', 'source_url', 'description', 'company_name'
            ])
            writer.writeheader()
            writer.writerows(all_leads)
        print(f"\n📁 Exported {len(all_leads)} leads to {export}")
    else:
        print("\n⚠️ No new leads exported.")

    print(f"\n🎯 Finished. New leads: {len(all_leads)} | Seen emails: {len(seen_emails)}")
    if failed_urls:
        print(f"\n⚠️ Skipped {len(failed_urls)} failed pages:")
        for url in failed_urls:
            print(f" - {url}")

    return all_leads


def save_lead_with_context(email, url, niche, description="", company_name=""):
    """Enhanced save function that includes context for personalization"""
    try:
        Lead.objects.create(
            username=email.split('@')[0],
            email=email,
            niche=niche,
            source_url=url,
            business_description=description,
            company_name=company_name,

        )
        return True
    except Exception as e:
        print(f"⚠️ Failed to save lead: {e}")
        return False



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dork", type=str, help="Manual Bing dork query", default=None)
    parser.add_argument("--niche", type=str, help="Niche name to tag emails with", default="manual")
    parser.add_argument("--limit", type=int, help="Max emails to save", default=25)
    parser.add_argument("--export", type=str, help="CSV filename to export", default=None)
    args = parser.parse_args()

    if args.dork:
        run_scraper([args.dork], limit=args.limit, export=args.export)
    else:
        run_scraper(niches=[
            "online fitness coach",
            "personal trainer",
            "weight loss coach",
            "female fitness trainer",
            "nutrition coach"
        ], limit=args.limit, export=args.export)

