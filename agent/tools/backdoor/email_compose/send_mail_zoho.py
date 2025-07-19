import smtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()
EMAIL_ADDRESS = os.getenv("ZOHO_EMAIL")
EMAIL_PASSWORD = os.getenv("zoho_app_password")
openai.api_key = os.getenv("OPENAI_API_KEY")


def generate_personalized_email(lead):
    """
    lead: dict with keys - name, email, website, bio, niche
    """
    prompt = f"""
    You are a cold email expert. Write a short, highly personalized cold outreach email.

    Lead info:
    Name: {lead.get('name')}
    Email: {lead.get('email')}
    Bio: {lead.get('bio')}
    Website: {lead.get('website')}
    Niche: {lead.get('niche')}

    Tone: Warm, confident, natural. Avoid sounding like spam. Max 100 words.

    Output Format:
    SUBJECT: <subject line>
    BODY: <email body>
    """

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    raw_output = response.choices[0].message.content
    lines = raw_output.strip().split("\n", 1)
    subject = lines[0].replace("SUBJECT:", "").strip()
    body = lines[1].replace("BODY:", "").strip()

    return subject, body


def send_email(to_email, subject, body):
    msg = EmailMessage()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.set_content(body)

    with smtplib.SMTP('smtp.zoho.com', 587) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)
        print(f"✅ Sent to {to_email}")


def send_to_lead(lead):
    subject, body = generate_personalized_email(lead)
    send_email(lead['email'], subject, body)


# Sample lead to test
if __name__ == "__main__":
    test_lead = {
        "name": "Daniel",
        "email": "daniel@example.com",
        "bio": "Fitness coach helping busy dads get back in shape.",
        "website": "https://fitwithdan.com",
        "niche": "Fitness & Wellness"
    }

    send_to_lead(test_lead)
