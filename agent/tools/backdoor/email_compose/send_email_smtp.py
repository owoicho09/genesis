

from django.core.mail import send_mail
from django.conf import settings
import openai

try:
    import django

    django.setup()
    from agent.models import Lead  # Replace 'your_app' with your actual app name

    print("✅ Django setup successful")
except Exception as e:
    print(f"❌ Django setup failed: {e}")
    sys.exit(1)



def generate_personalized_email(niche):
    """
    lead: dict with keys - name, email, website, bio, niche
    """
    lead = Lead.objects.filter(niche=niche,email_sent=False)

    prompt = f"""
    You are a cold email expert. Write a short, highly personalized cold outreach email.

    Lead info:
    Name: {lead.username}
    Email: {lead.email}
    Bio: {lead.bio if lead.bio else lead.business_description}
    Niche: {lead.niche}

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



def send_scraping_update(subject: str, message: str):
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=['michaelogaje033@gmail.com'],
        fail_silently=False
    )







