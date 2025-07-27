import os
import sys
import openai
import datetime
import subprocess
import re
import json
import logging
import time
import requests
from pathlib import Path
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.utils.text import slugify

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup Django
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

try:
    import django

    django.setup()
    from agent.models import Product

    application = get_wsgi_application()
except Exception as e:
    logger.error(f"Django setup failed: {e}")
    sys.exit(1)

# OpenAI configuration
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    logger.error("OPENAI_API_KEY not found in environment variables")
    sys.exit(1)


# Environment-safe config
def get_seo_repo_path():
    return os.getenv("SEO_BLOG_REPO") or os.path.join(PROJECT_ROOT, "seo-blog")


SEO_REPO_PATH = get_seo_repo_path()
POSTS_DIR = os.path.join(SEO_REPO_PATH, '_posts')

BLOG_CONFIG = {
    'seo_blog_repo': SEO_REPO_PATH,
    'posts_dir': POSTS_DIR,
    'github_pages_url': 'https://owoicho09.github.io/seo-blog',
    'default_author': 'Genesis Ai',
    'default_category': 'products',
    'max_retries': 3,
    'build_wait_time': 300  # 5 minutes max wait for GitHub Pages build
}

from difflib import SequenceMatcher


def normalize(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def fuzzy_score(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


class SEOBlogGenerator:
    def __init__(self, config=None):
        self.config = {**BLOG_CONFIG, **(config or {})}
        self.ensure_posts_directory()

    def ensure_posts_directory(self):
        Path(self.config['posts_dir']).mkdir(parents=True, exist_ok=True)

    def fetch_product(self, name):
        all_products = Product.objects.all()
        if not all_products:
            logger.warning("⚠️ No products in the database")
            return None

        scored = [
            (product, fuzzy_score(name, product.name))
            for product in all_products
        ]

        scored.sort(key=lambda x: x[1], reverse=True)
        best_match, score = scored[0]
        if score < 0.4:
            logger.warning(f"⚠️ Low match confidence ({score:.2f}) for: {name}")
            return None

        logger.info(f"✅ Matched '{name}' to product: '{best_match.name}' (score: {score:.2f})")
        return best_match

    def generate_seo_keywords(self, topic, product_name):
        keyword_prompt = f"""
        Generate 10-15 SEO keywords for a blog post about "{topic}" related to the product "{product_name}".
        Return only a comma-separated list of keywords, no explanations.
        Focus on long-tail keywords that users might search for.
        """
        try:
            print('Generating keywords...')
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": keyword_prompt}],
                temperature=0.3,
                max_tokens=200
            )
            print('keywords generated')
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate keywords: {e}")
            return f"{topic}, {product_name}, review, guide, tips"

    def generate_blog_post(self, product, topic):
        keywords = self.generate_seo_keywords(topic, product.name)
        prompt = f"""
          Write a comprehensive, SEO-optimized blog post (1500–2000 words) that directly answers the question: "{topic}".

    - Make the post **educational, practical, and solution-focused** — like a fitness mentor guiding busy professionals.
    - **Do not sell or promote** directly. Avoid phrases like “buy now” or “get yours”.
    - Introduce the product **"{product.name}"** as a **solution** or **tool** in the context of the topic — **strategically placed**:
        - Once in the early-middle as a casual mention.
        - Again in the **middle** when discussing practical steps.
        - And finally in the **conclusion** as a helpful recommendation.
    - Naturally insert this product link **inside a sentence**, like a helpful reference: `{product.url}`
    - Avoid repeating the product name too many times — vary your language.

    Format:
    - Use Markdown
    - Use informative subheadings (##)
    - Include bullets or numbered steps where helpful
    - Keep the tone clear, friendly, and helpful — like a fitness advisor writing for busy professionals

    Output:
    - Return only the Markdown blog post content
    - No frontmatter, no explanation
    """

        try:
            print('Generating blog post...')

            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=4000
            )
            print('Blog generated successfully')
            content = response.choices[0].message.content.strip()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {
                    "title": topic.title(),
                    "meta_description": f"Complete guide to {topic}.",
                    "content": content,
                    "keywords": keywords.split(", "),
                    "word_count": len(content.split())
                }
        except Exception as e:
            logger.error(f"Failed to generate blog post: {e}")
            raise

    def create_jekyll_post(self, blog_data, product):
        today = datetime.date.today()
        title = blog_data.get('title', 'Untitled Post')
        slug = slugify(title)
        filename = os.path.join(self.config['posts_dir'], f"{today}-{slug}.md")

        # ✅ Properly aligned frontmatter with no YAML indentation issues
        frontmatter = f"""---
layout: post
title: "{title}"
description: "{blog_data.get('meta_description', '')}"
date: {today.strftime('%Y-%m-%d')} 12:00:00 +0100
last_modified_at: {today.strftime('%Y-%m-%d')} 12:00:00 +0100
categories: [{self.config['default_category']}]
tags: {json.dumps(blog_data.get('keywords', [])[:10])}
author: 
  name: {self.config['default_author']}
  url: {self.config['github_pages_url']}
permalink: /{today.strftime('%Y/%m/%d')}/{slug}/
canonical_url: "{self.config['github_pages_url']}/{today.strftime('%Y/%m/%d')}/{slug}/"

seo:
  type: BlogPosting
  name: "{title}"
  headline: "{title}"
  description: "{blog_data.get('meta_description', '')}"
  image: 
    - "{self.config['github_pages_url']}/assets/images/default-blog-image.jpg"
  datePublished: {today.strftime('%Y-%m-%d')}T12:00:00+01:00
  dateModified: {today.strftime('%Y-%m-%d')}T12:00:00+01:00
  author:
    "@type": Person
    name: {self.config['default_author']}
  publisher:
    "@type": Organization
    name: Genesis Blog
    url: {self.config['github_pages_url']}

og:
  title: "{title}"
  description: "{blog_data.get('meta_description', '')}"
  image: "{self.config['github_pages_url']}/assets/images/default-blog-image.jpg"
  url: "{self.config['github_pages_url']}/{today.strftime('%Y/%m/%d')}/{slug}/"
  type: article

twitter:
  card: summary_large_image
  title: "{title}"
  description: "{blog_data.get('meta_description', '')}"
  image: "{self.config['github_pages_url']}/assets/images/default-blog-image.jpg"

sitemap:
  priority: 0.8
  changefreq: 'weekly'
  lastmod: {today.strftime('%Y-%m-%d')}

reading_time: {blog_data.get('word_count', 1500) // 200} min read
word_count: {blog_data.get('word_count', 1500)}
---

"""

        full_content = frontmatter + blog_data.get('content', '')
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(full_content)

        logger.info(f"📄 Created blog post: {filename}")
        return filename, slug

    def push_to_github(self, filename, commit_msg):
        repo_path = self.config['seo_blog_repo']
        try:
            # Check git status first
            result = subprocess.run(['git', 'status', '--porcelain'],
                                    capture_output=True, text=True, cwd=repo_path)
            if result.stdout.strip():
                logger.info("📝 Uncommitted changes detected, stashing...")
                subprocess.run(['git', 'stash'], check=True, cwd=repo_path)

            # Ensure we are on 'main' branch
            subprocess.run(['git', 'checkout', 'main'], check=True, cwd=repo_path)

            # Pull latest changes from origin/main
            subprocess.run(['git', 'pull', '--rebase', 'origin', 'main'], check=True, cwd=repo_path)

            # Apply stashed changes back (if any)
            try:
                subprocess.run(['git', 'stash', 'pop'], check=True, cwd=repo_path)
            except subprocess.CalledProcessError:
                # No stash to pop, which is fine
                pass

            # ✅ Add this before committing
            subprocess.run(['git', 'config', 'user.name', 'Genesis AI Bot'], check=True, cwd=repo_path)
            subprocess.run(['git', 'config', 'user.email', 'bot@genesis.ai'], check=True, cwd=repo_path)
     
            # Add and commit
            subprocess.run(['git', 'add', filename], check=True, cwd=repo_path)
            # Check if there are changes to commit
            result = subprocess.run(['git', 'diff', '--cached', '--quiet'],
                                    cwd=repo_path)
            if result.returncode != 0:  # There are changes to commit
                subprocess.run(['git', 'commit', '-m', commit_msg], check=True, cwd=repo_path)
                subprocess.run(['git', 'push'], check=True, cwd=repo_path)
                logger.info(f"✅ Successfully pushed to GitHub: {commit_msg}")
                return True
            else:
                logger.info("ℹ️ No changes to commit")
                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")
            return False

    def generate_blog_url(self, filename, slug=None):
        """Generate the correct URL for the blog post"""
        if slug:
            # Use the provided slug directly
            today = datetime.date.today()
            return f"{self.config['github_pages_url']}/{today.strftime('%Y/%m/%d')}/{slug}/"

        # Fallback to parsing filename
        basename = os.path.basename(filename).replace('.md', '')
        parts = basename.split('-', 3)
        if len(parts) >= 4:
            year, month, day = parts[0], parts[1], parts[2]
            slug = parts[3]
            return f"{self.config['github_pages_url']}/{year}/{month}/{day}/{slug}/"

        logger.warning(f"Could not parse filename for URL generation: {basename}")
        return f"{self.config['github_pages_url']}/"

    def wait_for_deployment(self, url, max_wait_time=300):
        """Wait for GitHub Pages to deploy the new post"""
        logger.info(f"⏳ Waiting for deployment at: {url}")
        start_time = time.time()

        while time.time() - start_time < max_wait_time:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"✅ Page is live: {url}")
                    return True
                elif response.status_code == 404:
                    logger.info("⏳ Still building... waiting 30 seconds")
                    time.sleep(30)
                else:
                    logger.info(f"⏳ Got status {response.status_code}, waiting...")
                    time.sleep(30)
            except requests.RequestException as e:
                logger.info(f"⏳ Request failed ({e}), waiting...")
                time.sleep(30)

        logger.warning(f"⚠️ Timeout waiting for deployment. URL might still work: {url}")
        return False

    def run(self, product_name, topic, wait_for_deploy=True):
        logger.info(f"Starting blog generation for product: {product_name}, topic: {topic}")
        product = self.fetch_product(product_name)
        if not product:
            logger.error(f"❌ No matching product found for: {product_name}")
            return False

        blog_data = self.generate_blog_post(product, topic)
        filename, slug = self.create_jekyll_post(blog_data, product)
        commit_msg = f"Add SEO blog: {blog_data.get('title', topic)}"

        if self.push_to_github(filename, commit_msg):
            url = self.generate_blog_url(filename, slug)
            logger.info(f"🔗 URL: {url}")

            if wait_for_deploy:
                self.wait_for_deployment(url, self.config['build_wait_time'])
            else:
                logger.info(
                    "ℹ️ Skipping deployment wait. URL will be available after GitHub Pages builds (1-5 minutes)")

            return True
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate SEO blog posts for products")
    parser.add_argument("--product", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--config", help="Path to config JSON")
    parser.add_argument("--no-wait", action="store_true", help="Don't wait for deployment")
    args = parser.parse_args()

    config = {}
    if args.config and os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config = json.load(f)

    generator = SEOBlogGenerator(config)
    success = generator.run(args.product, args.topic, wait_for_deploy=not args.no_wait)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()