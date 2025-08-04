# 🧠 Genesis

**Genesis** is a full-stack AI automation engine for digital product creators.
It combines scraping, intelligent cold outreach, SEO content publishing, and GPT task execution — all within a unified, programmable framework.

Whether you're trying to:

* 🚀 Discover high-signal leads in a niche (e.g. real estate agents in NYC)
* ✍🏾 Publish SEO blog content that ranks and sells your products
* 📬 Automate daily cold outreach using smart personalization

**Genesis makes it all possible.**

---

## 🚀 Core Features


### GPT-Powered Chatbot (API Endpoint)
Interact with Genesis via a local chatbot:

bash
Copy
Edit
http://localhost:8000/api/chat/
Accepts natural commands like:
```
scrape google map for dentists in Miami

publish a blog on healthy sleep habits for our pillow product

launch an ad campaign for [product_name]
```

### ✅ 1. Google Maps Scraper for Lead Generation

Use Genesis to extract niche-targeted local businesses from Google Maps — great for B2B outreach, partnerships, or market research.

**Prompt Example:**

```
scrape google map for [real estate agent in new york]
```

Genesis will:

* Search Google Maps using Playwright
* Visit each business profile and extract:

  * Business name
  * Email (if available)
  * Phone number
  * Website
  * Reviews & rating
* Filter and validate quality leads
* Store results in the Django database or Postgres for follow-up

---

### 📝 2. SEO Blog Publisher with Product Linking

Automate your SEO content engine. Genesis can:

* Generate GPT-powered articles
* Embed product links from your database
* Auto-publish to GitHub Pages in Markdown format

**Prompt Example:**

```
publish a blog on [how real estate agents can get more clients]
```

Or with product linking:

```
publish a blog on [fitness content marketing] for product [AI Fitness Kit]
```

Genesis will:

* Write the blog using OpenAI
* Fetch product info (title, summary, URL) from the DB
* Insert call-to-actions with links
* Auto-push the Markdown file to your GitHub Pages blog

---

### 📩 3. Smart Cold Outreach System

Run intelligent, personalized email outreach campaigns on autopilot:

* Uses rotating SMTP inboxes (Zoho, Gmail, etc.)
* Sends 1 email every 10 minutes to avoid spam filters
* Caps at 30 emails per inbox/day
* GPT personalizes each message using scraped data (e.g. website, reviews)

Great for:

* Coaches
* SaaS founders
* Local service providers
* Niche B2B segments

---

## ⚙️ Tools Used

| Tool                            | Purpose                                         |
| ------------------------------- | ----------------------------------------------- |
| **Python 3.10+**                | Core scripting and automation logic             |
| **Django**                      | ORM and backend management                      |
| **Playwright**                  | Google Maps scraping and browser automation     |
| **OpenAI API (GPT-4)**          | Blog/article generation, lead filtering, emails |
| **GitHub Pages**                | SEO blog publishing                             |
| **Celery + Redis** *(optional)* | Background tasks and email scheduling           |

---

## 📁 Project Structure

```
genesis/
│
├── core/               # Django project core
├── scraper/            # Google Maps scraping logic (Playwright)
├── outreach/           # Email rotation + GPT personalization
├── blog/               # SEO blog generation and GitHub publishing
├── rag_engine/         # Prompt interpretation and decision layer
├── run_rag.py          # Entry point to run Genesis
└── templates/          # Reusable templates for email/blog
```

---

## 🛠 How to Run Genesis Locally

### 1. Clone the Repository

```bash
git clone https://github.com/owoicho09/genesis.git
cd genesis
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
playwright install
```

### 3. Configure Environment

Create a `.env` file:

```
OPENAI_API_KEY=your-key
EMAIL_HOST_USER=your-email
EMAIL_HOST_PASSWORD=your-password
GITHUB_TOKEN=your-github-token
GITHUB_REPO=your-github-username/seo-blog
```

### 4. Run Genesis

```bash
python run_rag.py
```

Example prompts:

```
scrape google map for [fitness coach in austin texas]
publish a blog on [lead generation tips for yoga coaches] for product [Yoga Growth Kit]
```

---

## 📌 Licensing

This project is licensed under the **Business Source License (BUSL)**.
You may use and modify Genesis for personal or educational purposes.

**Commercial use requires permission.**
Reach out: [michaelogaje033@gmail.com](mailto:michaelogaje033@gmail.com)

---

## 🙋‍♂️ About the Creator

**Owoicho Michael Ogaje**

* Python Developer & Ai Automation Engineer
* Founder of [Genesis.ai](https://github.com/owoicho09/genesis)
* Creator of [Unitoria](https://unitoriamvp.vercel.app/), a student-centered ed-tech platform

**Contact:** [michaelogaje033@gmail.com](mailto:michaelogaje033@gmail.com)
**Location:** Abuja, Nigeria

---

## 💬 Questions?

* Open an issue
* Connect on [LinkedIn](https://www.linkedin.com/in/michael-ogaje-862765377/)
* Or email directly to collaborate or get commercial rights

---

> "Genesis shows what’s possible when scraping, AI, and automation come together to build real growth systems."
