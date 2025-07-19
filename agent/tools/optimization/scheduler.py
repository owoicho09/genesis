from typing import List, Dict
from langchain.tools import tool
from agent.tools.optimization.metric_fetcher import fetch_campaign_metrics
from agent.tools.optimization.metrics_analyzer import analyze_campaign_metrics
from agent.tools.optimization.decision_maker import decide_campaign_action
from agent.tools.optimization.campaign_modifier import modify_campaign_from_decision
from agent.models import Campaign

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.core.mail import send_mail
from django.conf import settings
from typing import Dict


from_email = settings.FROM_EMAIL
to_email = settings.FROM_EMAIL  # Send to yourself if not specified


def run_optimization():
    """
    Runs the full optimization pipeline daily across all active campaigns.
    Fetches metrics, analyzes them, makes decisions, and applies campaign modifications.
    Returns a report of successes and failures.
    """


    report = {"optimized": [], "skipped": [], "failed": []}

    active_campaigns = Campaign.objects.filter(status="active")  # or your custom filter

    for campaign in active_campaigns:
        try:
            # 1. Fetch metrics
            metrics = fetch_campaign_metrics(campaign.meta_campaign_id)
            if "error" in metrics:
                report["skipped"].append({campaign.meta_campaign_id: metrics["error"]})
                continue

            # 2. Analyze
            analysis = analyze_campaign_metrics(metrics)
            if analysis.get("score", 0) < 20:  # Optional: skip dead campaigns
                report["skipped"].append({campaign.meta_campaign_id: "Low health score"})
                continue

            # 3. Decide
            decision = decide_campaign_action(metrics, analysis)

            # 4. Modify campaign
            result = modify_campaign_from_decision(decision)
            report["optimized"].append({
                "campaign_id": campaign.meta_campaign_id,
                "decision": decision.get("decision"),
                "result": result
            })

        except Exception as e:
            report["failed"].append({campaign.meta_campaign_id: str(e)})

    return report




@tool
def send_campaign_alert(subject: str, html_message: str) -> Dict:
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




