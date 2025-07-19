

from django.core.mail import send_mail
from django.conf import settings




def send_scraping_update(subject: str, message: str):
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=['michaelogaje033@gmail.com'],
        fail_silently=False
    )



def send_emails(subject: str, message: str,recipient_list: list):
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=False
    )





