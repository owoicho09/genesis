import smtplib
import os
from dotenv import load_dotenv
load_dotenv()

username = os.getenv("ZOHO_EMAIL")
password = os.getenv("zoho_app_password")

try:
    smtp = smtplib.SMTP("smtp.zoho.com", 587)
    smtp.ehlo()
    smtp.starttls()
    smtp.login(username, password)
    smtp.sendmail(username, username, "Subject: Test\n\nThis is a test email from script.")
    smtp.quit()
    print("✅ Email sent successfully")
except Exception as e:
    print(f"❌ SMTP failed: {e}")
