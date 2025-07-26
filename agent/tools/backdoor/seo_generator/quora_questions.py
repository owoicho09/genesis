import time
import random
from playwright.sync_api import sync_playwright
import urllib.parse


def scrape_quora_questions(keyword, max_results=10, headless=True):
    """
    Scrape Quora questions related to a keyword for blog topic generation

    Args:
        keyword (str): Search keyword/topic
        max_results (int): Maximum number of questions to retrieve
        headless (bool): Run browser in headless mode

    Returns:
        list: List of dictionaries containing question text and URLs
    """
    questions = []

    try:
        with sync_playwright() as p:
            # Launch browser with realistic settings
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--disable-extensions',
                ]
            )

            # Create context with realistic user agent and extra headers
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1366, 'height': 768},
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )

            page = context.new_page()

            # Block images and ads to speed up loading
            page.route("**/*.{png,jpg,jpeg,gif,svg,css}", lambda route: route.abort())

            # Encode the search query properly
            encoded_keyword = urllib.parse.quote_plus(keyword)
            search_url = f"https://www.quora.com/search?q={encoded_keyword}&type=question"

            print(f"Searching Quora for: {keyword}")
            print(f"URL: {search_url}")

            # Navigate to search page
            page.goto(search_url, timeout=60000)

            # Wait for dynamic content to load
            page.wait_for_timeout(5000)

            # Scroll to load more content
            for i in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

            # More specific and updated selectors for Quora questions
            selectors_to_try = [
                # Updated selectors based on current Quora structure
                "div[class*='Question'] a",
                "a[class*='question_link']",
                "span[class*='question_text'] a",
                "div[role='button'] a[href*='/']",
                "a[href*='/questions/']",
                "a[href*='/unanswered/']",
                ".puppeteer_test_question_title a",
                "span.puppeteer_test_question_title",
            ]

            question_elements = []

            # Try different selectors
            for selector in selectors_to_try:
                try:
                    elements = page.query_selector_all(selector)
                    if elements:
                        question_elements = elements
                        print(f"Found {len(elements)} elements with selector: {selector}")
                        break
                except Exception as e:
                    continue

            # Fallback: get all text elements and filter for questions
            if not question_elements:
                print("Trying fallback approach...")
                # Get all elements with text
                all_elements = page.query_selector_all("span, div, a, p")
                question_elements = []

                for el in all_elements:
                    try:
                        text = el.inner_text().strip()
                        if (text and
                                len(text) > 10 and
                                len(text) < 300 and
                                ("?" in text or
                                 any(word in text.lower() for word in
                                     ["what", "how", "why", "when", "where", "which", "should", "can", "is", "are",
                                      "do", "does"]))):
                            question_elements.append(el)
                    except:
                        continue

            # Extract and filter questions
            seen_questions = set()

            for el in question_elements:
                try:
                    text = el.inner_text().strip()

                    if not text:
                        continue

                    # Filter out JavaScript, CSS, and non-question content
                    if any(skip in text.lower() for skip in [
                        'frontend', 'window.', 'function', 'checkpoint', 'javascript',
                        'css', 'html', 'script', 'var ', 'let ', 'const ', 'return',
                        'document.', 'query', 'selector', 'element', 'api', 'json'
                    ]):
                        continue

                    # Ensure it looks like a real question
                    if not (("?" in text) or
                            (len(text) > 15 and any(word in text.lower() for word in [
                                "what", "how", "why", "when", "where", "which",
                                "should", "can", "is", "are", "do", "does", "will", "would"
                            ]))):
                        continue

                    # Length check
                    if len(text) < 10 or len(text) > 300:
                        continue

                    # Avoid duplicates
                    if text in seen_questions:
                        continue

                    # Try to get the URL
                    href = ""
                    try:
                        if el.tag_name.lower() == 'a':
                            href = el.get_attribute("href") or ""
                        else:
                            parent_link = el.query_selector("ancestor::a") or el.query_selector("a")
                            if parent_link:
                                href = parent_link.get_attribute("href") or ""
                    except:
                        href = search_url  # Fallback to search URL

                    # Build full URL
                    if href.startswith('/'):
                        full_url = f"https://www.quora.com{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = search_url

                    questions.append({
                        "question": text,
                        "url": full_url,
                        "keyword": keyword
                    })

                    seen_questions.add(text)
                    print(f"Found question: {text[:80]}...")

                    if len(questions) >= max_results:
                        break

                except Exception as e:
                    continue

            browser.close()

    except Exception as e:
        print(f"Error during scraping: {e}")
        return []

    print(f"Successfully scraped {len(questions)} questions for keyword: {keyword}")
    return questions


def scrape_quora_topics(main_topic, max_questions_per_subtopic=5):
    """
    Get blog topics by first finding Quora topics, then questions within those topics

    Args:
        main_topic (str): Main topic to explore
        max_questions_per_subtopic (int): Max questions per subtopic

    Returns:
        dict: Organized topics and questions
    """

    blog_topics = {
        "main_topic": main_topic,
        "subtopics": []
    }

    # First, search for the main topic to find related questions
    main_questions = scrape_quora_questions(main_topic, max_results=15)

    if main_questions:
        blog_topics["main_questions"] = main_questions

        # Extract potential subtopics from questions
        subtopics = set()
        for q in main_questions:
            question_text = q["question"].lower()
            # Simple keyword extraction (you can enhance this)
            words = question_text.split()
            for word in words:
                if len(word) > 4 and word not in ['what', 'how', 'when', 'where', 'why', 'which', 'should', 'would',
                                                  'could']:
                    subtopics.add(word.capitalize())

        # Limit subtopics and get questions for each
        for subtopic in list(subtopics)[:5]:  # Limit to 5 subtopics
            subtopic_questions = scrape_quora_questions(f"{main_topic} {subtopic}",
                                                        max_results=max_questions_per_subtopic)
            if subtopic_questions:
                blog_topics["subtopics"].append({
                    "topic": subtopic,
                    "questions": subtopic_questions
                })

    return blog_topics


def format_for_blog_generation(scraped_data):
    """
    Format scraped questions into blog-ready topics

    Args:
        scraped_data (list or dict): Output from scraping functions

    Returns:
        list: Formatted blog topics
    """

    blog_topics = []

    if isinstance(scraped_data, list):
        # Simple list of questions
        for item in scraped_data:
            blog_topics.append({
                "title": item["question"],
                "angle": "Answer the question comprehensively",
                "keywords": item.get("keyword", ""),
                "source_url": item["url"]
            })

    elif isinstance(scraped_data, dict) and "main_questions" in scraped_data:
        # Structured topic data
        main_topic = scraped_data["main_topic"]

        for question in scraped_data["main_questions"]:
            blog_topics.append({
                "title": f"Complete Guide: {question['question']}",
                "angle": f"Comprehensive guide about {main_topic}",
                "keywords": main_topic,
                "source_url": question["url"]
            })

        for subtopic_data in scraped_data["subtopics"]:
            subtopic = subtopic_data["topic"]
            for question in subtopic_data["questions"]:
                blog_topics.append({
                    "title": question["question"],
                    "angle": f"Focus on {subtopic} aspect of {main_topic}",
                    "keywords": f"{main_topic}, {subtopic}",
                    "source_url": question["url"]
                })

    return blog_topics


def scrape_quora_via_google(keyword, max_results=10):
    """
    Alternative approach: Use Google to find Quora questions
    More reliable than direct Quora scraping
    """
    questions = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = context.new_page()

            # Search Google for Quora questions about the topic
            google_query = f'site:quora.com "{keyword}" "?"'
            encoded_query = urllib.parse.quote_plus(google_query)
            google_url = f"https://www.google.com/search?q={encoded_query}&num=20"

            print(f"Searching Google for Quora questions: {keyword}")
            page.goto(google_url, timeout=30000)
            page.wait_for_timeout(3000)

            # Extract search results
            search_results = page.query_selector_all("h3")

            for result in search_results:
                try:
                    title = result.inner_text().strip()
                    parent_link = result.query_selector("xpath=ancestor::a")

                    if parent_link and title:
                        url = parent_link.get_attribute("href")

                        # Clean up Google redirect URLs
                        if url and "quora.com" in url:
                            # Extract actual Quora URL from Google redirect
                            import re
                            quora_url_match = re.search(r'https://www\.quora\.com[^&]*', url)
                            if quora_url_match:
                                clean_url = quora_url_match.group(0)

                                # Filter for question-like titles
                                if (len(title) > 15 and
                                        ("?" in title or
                                         any(word in title.lower() for word in
                                             ["what", "how", "why", "when", "where"]))):

                                    questions.append({
                                        "question": title,
                                        "url": clean_url,
                                        "keyword": keyword
                                    })

                                    print(f"Found: {title[:60]}...")

                                    if len(questions) >= max_results:
                                        break

                except Exception as e:
                    continue

            browser.close()

    except Exception as e:
        print(f"Error in Google search approach: {e}")
        return []

    return questions


def generate_question_variations(base_keyword):
    """
    Generate different question variations for a topic
    Useful when scraping returns limited results
    """
    question_starters = [
        f"What is {base_keyword}",
        f"How does {base_keyword} work",
        f"Why is {base_keyword} important",
        f"What are the benefits of {base_keyword}",
        f"How to learn {base_keyword}",
        f"What are the challenges of {base_keyword}",
        f"How to get started with {base_keyword}",
        f"What are the best practices for {base_keyword}",
        f"What are the common mistakes in {base_keyword}",
        f"How to improve {base_keyword} skills"
    ]

    variations = []
    for starter in question_starters:
        variations.append({
            "question": starter + "?",
            "url": f"https://www.quora.com/search?q={urllib.parse.quote_plus(starter)}",
            "keyword": base_keyword
        })

    return variations


# Example usage
if __name__ == "__main__":
    keyword = "machine learning"

    print("=== Method 1: Direct Quora Scraping ===")
    questions1 = scrape_quora_questions(keyword, max_results=5)

    print(f"\n=== Method 2: Google Search for Quora Questions ===")
    questions2 = scrape_quora_via_google(keyword, max_results=10)

    print(f"\n=== Method 3: Generated Question Variations ===")
    questions3 = generate_question_variations(keyword)

    # Combine all methods
    all_questions = questions1 + questions2 + questions3[:5]  # Limit generated ones

    print(f"\n=== Combined Results ({len(all_questions)} questions) ===")
    for i, q in enumerate(all_questions[:10], 1):  # Show first 10
        print(f"{i}. {q['question']}")
        print(f"   Source: {q['url'][:50]}...\n")

    # Format for blog generation
    blog_topics = format_for_blog_generation(all_questions)

    print(f"\n=== Ready for Blog Generation ===")
    print(f"Total blog topics ready: {len(blog_topics)}")
    for topic in blog_topics[:3]:
        print(f"- {topic['title']}")
        print(f"  Keywords: {topic['keywords']}\n")