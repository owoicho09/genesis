from agent import models as agent_models
from django.utils import timezone
import requests
import json
import os
from typing import List

import glob
from dotenv import load_dotenv
# imports for langchain, plotly and Chroma
from agent.tools.system_prompt import analyze_system_prompt
from openai import OpenAI
from datetime import datetime, timedelta, timezone
from langchain.tools import tool

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import CharacterTextSplitter,RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
import numpy as np
import plotly.graph_objects as go
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain
from langchain.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores.utils import filter_complex_metadata
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.tools import tool
from typing import Dict

from agent.tools.rag_setup import setup_product_rag_chroma
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI





from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.ad import Ad




load_dotenv()
db_name = os.getenv("CHROMA_DB_BASE_PATH", "./chroma_db")
persist_dir = db_name  # or another env variable if you want
MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")


# 🔐 Your credentials
ad_account_id = os.getenv('fb_ad_account_id')
app_id = os.getenv('fb_app_id')
app_secret = os.getenv('fb_app_secret')
page_id = os.getenv('fb_page_id')



BASE_URL = "https://graph.facebook.com/v23.0"
ACCESS_TOKEN = os.getenv("SYSTEM_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("fb_ad_account_id")



@tool
def decide_campaign_action(metrics: dict, analysis: dict) -> dict:
    """
    Decides the best campaign action based on metrics and analysis (e.g., pause, scale, edit, optimize).
    """

    # ----------------------------
    # Extract Core Metrics
    # ----------------------------
    roas = metrics.get("purchase_roas", 0)
    spend = metrics.get("spend", 0)
    conversions = metrics.get("purchases", 0)
    cpc = metrics.get("cpc", 0)
    ctr = metrics.get("ctr", 0)
    frequency = metrics.get("frequency", 0)
    days_running = metrics.get("days_running", 1)
    clicks = metrics.get("clicks", 0)
    impressions = metrics.get("impressions", 0)

    # Analysis outputs
    score = analysis.get("score", 0)
    status = analysis.get("status", "")
    meta_campaign_id = analysis.get("meta_campaign_id", "")
    flags = analysis.get("flags", [])
    recommendations = analysis.get("recommendations", [])
    priority_actions = analysis.get("priority_actions", [])

    # Derived metrics
    daily_spend = spend / days_running if days_running > 0 else spend
    conversion_rate = (conversions / clicks * 100) if clicks > 0 else 0

    # ----------------------------
    # Decision Logic (Priority Order)
    # ----------------------------

    # 🚨 CRITICAL: Immediate pause situations
    if _should_pause_immediately(spend, conversions, roas, flags, days_running):
        return _create_decision("pause",
                                _get_pause_reason(spend, conversions, roas, flags),
                                metrics, analysis, "critical")

    # 🎯 SCALING: Profitable campaigns ready to grow
    if _should_scale(roas, score, conversions, flags, spend, days_running):
        return _create_decision("scale",
                                _get_scale_reason(roas, score, conversions),
                                metrics, analysis, "high")

    # 🧬 CLONING: Excellent performers for horizontal scaling
    if _should_clone(status, roas, conversions, score, flags):
        return _create_decision("clone",
                                _get_clone_reason(roas, conversions, score),
                                metrics, analysis, "high")

    # 🔄 CREATIVE REFRESH: Creative issues detected
    if _needs_creative_refresh(flags, ctr, frequency, conversions, clicks):
        return _create_decision("edit_creative",
                                _get_creative_reason(flags, ctr, frequency),
                                metrics, analysis, "medium")

    # 🎯 AUDIENCE OPTIMIZATION: Targeting issues
    if _needs_audience_change(flags, cpc, conversion_rate, roas):
        return _create_decision("change_audience",
                                _get_audience_reason(flags, cpc, conversion_rate),
                                metrics, analysis, "medium")

    # 🛠 OFFER OPTIMIZATION: Funnel issues
    if _needs_offer_revision(flags, ctr, conversion_rate, conversions, clicks):
        return _create_decision("revise_offer",
                                _get_offer_reason(flags, conversion_rate, ctr),
                                metrics, analysis, "medium")

    # 💰 BUDGET OPTIMIZATION: Spend efficiency issues
    if _needs_budget_optimization(daily_spend, roas, cpc, score):
        return _create_decision("optimize_budget",
                                _get_budget_reason(daily_spend, roas, cpc),
                                metrics, analysis, "low")

    # ⏳ WAIT: Early stage or insufficient data
    if _should_wait(spend, days_running, conversions, impressions):
        return _create_decision("wait",
                                _get_wait_reason(spend, days_running, conversions),
                                metrics, analysis, "low")

    # 🔧 DEFAULT: General optimization needed
    return _create_decision("edit_creative",
                            "Campaign performance needs improvement. Start with creative optimization.",
                            metrics, analysis, "medium")



@tool
def decide_all_active_campaign_metrics_actions(metrics_list: List[dict], analysis_list: List[dict]) -> List[dict]:
    """
    Decides actions for multiple campaigns using their metrics and analysis results.
    """
    decisions = []
    for metrics, analysis in zip(metrics_list, analysis_list):
        try:
            decision = decide_campaign_action(metrics, analysis)
            decisions.append(decision)
        except Exception as e:
            decisions.append({
                "meta_campaign_id": metrics.get("meta_campaign_id"),
                "error": f"Decision failed: {str(e)}"
            })
    return decisions



# ----------------------------
# Decision Logic Functions
# ----------------------------

def _should_pause_immediately(spend, conversions, roas, flags, days_running):
    """Determine if campaign should be paused immediately"""
    # High spend, no conversions, sufficient time
    if spend >= 15 and conversions == 0 and days_running >= 3:
        return True

    # Very high spend, terrible ROAS
    if spend >= 30 and roas < 0.5:
        return True

    # Critical flags
    critical_flags = ["zero_roas_high_spend", "no_conversions_significant_spend",
                      "multiple_issues", "critically_low_ctr"]
    if any(flag in flags for flag in critical_flags):
        return True

    return False


def _should_scale(roas, score, conversions, flags, spend, days_running):
    """Determine if campaign is ready for scaling"""
    # Strong performance indicators
    if (roas >= 4.0 and score >= 80 and conversions >= 5 and
            "scaling_opportunity" in flags and spend >= 30):
        return True

    # Good performance with proven data
    if (roas >= 3.5 and score >= 75 and conversions >= 3 and
            days_running >= 2 and spend >= 20):
        return True

    return False


def _should_clone(status, roas, conversions, score, flags):
    """Determine if campaign should be cloned"""
    # Excellent status with strong metrics
    if (status == "excellent" and roas >= 4.0 and
            conversions >= 5 and score >= 85):
        return True

    # Very strong performance
    if (roas >= 5.0 and conversions >= 3 and score >= 80 and
            "scaling_opportunity" in flags):
        return True

    return False


def _needs_creative_refresh(flags, ctr, frequency, conversions, clicks):
    """Determine if creative needs refreshing"""
    creative_flags = ["critically_low_ctr", "low_ctr", "creative_fatigue",
                      "severe_ad_fatigue", "weak_creative"]

    if any(flag in flags for flag in creative_flags):
        return True

    # Low CTR with decent spend
    if ctr < 0.9 and clicks > 50:
        return True

    # High frequency
    if frequency >= 3.0:
        return True

    return False


def _needs_audience_change(flags, cpc, conversion_rate, roas):
    """Determine if audience targeting needs change"""
    audience_flags = ["bad_audience_match", "high_cpc", "low_frequency_high_spend"]

    if any(flag in flags for flag in audience_flags):
        return True

    # High CPC with poor conversion
    if cpc > 1.5 and conversion_rate < 1.5:
        return True

    # Decent ROAS but expensive traffic
    if roas >= 2.0 and cpc > 2.0:
        return True

    return False


def _needs_offer_revision(flags, ctr, conversion_rate, conversions, clicks):
    """Determine if offer/landing page needs revision"""
    offer_flags = ["conversion_dropoff", "low_conversion_rate"]

    if any(flag in flags for flag in offer_flags):
        return True

    # Good traffic, poor conversion
    if ctr >= 1.5 and conversion_rate < 1.0 and clicks > 30:
        return True

    return False


def _needs_budget_optimization(daily_spend, roas, cpc, score):
    """Determine if budget needs optimization"""
    # High spend with mediocre performance
    if daily_spend > 20 and roas < 2.5 and score < 60:
        return True

    # Low spend with good performance (could increase)
    if daily_spend < 15 and roas > 4.0 and cpc < 0.8:
        return True

    return False


def _should_wait(spend, days_running, conversions, impressions):
    """Determine if we should wait for more data"""
    # Very new campaign
    if days_running < 2 and spend < 20:
        return True

    # Low spend, early stage
    if spend < 10 and conversions == 0 and impressions < 1000:
        return True

    return False


# ----------------------------
# Reason Generation Functions
# ----------------------------

def _get_pause_reason(spend, conversions, roas, flags):
    """Generate specific pause reason"""
    if spend >= 30 and conversions == 0:
        return f"🚨 CRITICAL: Spent ${spend:.0f} with zero conversions. Immediate pause required to prevent further loss."
    elif "multiple_issues" in flags:
        return "🚨 Multiple critical issues detected. Pause and restructure campaign completely."
    elif roas < 0.5 and spend >= 20:
        return f"🚨 Extremely poor ROAS ({roas:.2f}) with significant spend. Pause immediately."
    else:
        return "🚨 Campaign is actively losing money. Pause to prevent further losses."


def _get_scale_reason(roas, score, conversions):
    """Generate specific scaling reason"""
    return f"🚀 SCALE: Excellent performance (ROAS: {roas:.1f}x, Score: {score}/100, {conversions} conversions). Increase budget by 25-50%."


def _get_clone_reason(roas, conversions, score):
    """Generate specific cloning reason"""
    return f"🧬 CLONE: Outstanding performance (ROAS: {roas:.1f}x, {conversions} conversions). Duplicate with new audience/creative for horizontal scaling."


def _get_creative_reason(flags, ctr, frequency):
    """Generate specific creative refresh reason"""
    if "severe_ad_fatigue" in flags:
        return f"🎨 URGENT: Severe ad fatigue (frequency: {frequency:.1f}). Refresh creative immediately."
    elif "critically_low_ctr" in flags:
        return f"🎨 URGENT: CTR critically low ({ctr:.2f}%). Complete creative overhaul needed."
    elif ctr < 1.0:
        return f"🎨 Creative underperforming (CTR: {ctr:.2f}%). Test new hooks, visuals, and copy."
    else:
        return "🎨 Creative needs refresh. Test new angles and formats."


def _get_audience_reason(flags, cpc, conversion_rate):
    """Generate specific audience change reason"""
    if "bad_audience_match" in flags:
        return f"🎯 Audience mismatch: High CPC (${cpc:.2f}) with poor conversion rate ({conversion_rate:.1f}%). Refine targeting."
    elif cpc > 2.0:
        return f"🎯 CPC too high (${cpc:.2f}). Test more specific or less competitive audiences."
    else:
        return "🎯 Audience optimization needed. Test narrower targeting or new segments."


def _get_offer_reason(flags, conversion_rate, ctr):
    """Generate specific offer revision reason"""
    if "conversion_dropoff" in flags:
        return f"🛠 Good engagement (CTR: {ctr:.2f}%) but poor conversion ({conversion_rate:.1f}%). Optimize landing page/offer."
    else:
        return f"🛠 Low conversion rate ({conversion_rate:.1f}%). Review pricing, landing page, and value proposition."


def _get_budget_reason(daily_spend, roas, cpc):
    """Generate specific budget optimization reason"""
    if daily_spend > 10 and roas < 2.0:
        return f"💰 High daily spend (${daily_spend:.0f}) with mediocre ROAS. Reduce budget until optimized."
    elif daily_spend < 15 and roas > 3.5:
        return f"💰 Strong performance (ROAS: {roas:.1f}x) with low spend. Consider increasing budget."
    else:
        return "💰 Budget optimization needed for better efficiency."


def _get_wait_reason(spend, days_running, conversions):
    """Generate specific wait reason"""
    if days_running < 2:
        return f"⏳ Campaign too new ({days_running} days). Allow 2-3 days for optimization."
    elif spend < 10:
        return f"⏳ Insufficient spend (${spend:.0f}) for evaluation. Allow more data accumulation."
    else:
        return "⏳ Insufficient data. Monitor for 24-48 hours before making changes."


def _create_decision(decision, reason, metrics, analysis, priority):
    """Create standardized decision output"""
    roas = metrics.get("purchase_roas", 0)
    spend = metrics.get("spend", 0)
    conversions = metrics.get("purchases", 0)

    decision_data = {
        "meta_campaign_id": metrics.get("meta_campaign_id"),
        "decision": decision,
        "reason": reason,
        "priority": priority,
        "confidence": _calculate_confidence(metrics, analysis),
        "metrics_summary": {
            "roas": roas,
            "spend": spend,
            "conversions": conversions,
            "score": analysis.get("score", 0)
        },
        "profitability": "high" if roas >= 3.0 else "medium" if roas >= 1.5 else "low",
        "next_review": _get_next_review_timeframe(decision),
        "expected_outcome": _get_expected_outcome(decision, roas),
        "flags": analysis.get("flags", []),
        "priority_actions": analysis.get("priority_actions", []),
        "recommendations": analysis.get("recommendations", [])
    }
    from agent.tools.optimization.scheduler import send_campaign_alert

    send_campaign_alert(decision,reason)

    return decision_data


def _calculate_confidence(metrics, analysis):
    """Calculate confidence level in decision"""
    spend = metrics.get("spend", 0)
    conversions = metrics.get("purchases", 0)
    days_running = metrics.get("days_running", 1)

    if spend >= 30 and conversions >= 3 and days_running >= 3:
        return "high"
    elif spend >= 20 and days_running >= 2:
        return "medium"
    else:
        return "low"


#use this to perform scheduled optimization
def _get_next_review_timeframe(decision):
    """Get recommended next review timeframe"""
    timeframes = {
        "pause": "24 hours",
        "scale": "48-72 hours",
        "clone": "3-5 days",
        "edit_creative": "24-48 hours",
        "change_audience": "48-72 hours",
        "revise_offer": "24-48 hours",
        "optimize_budget": "48 hours",
        "wait": "24 hours"
    }
    return timeframes.get(decision, "24-48 hours")


def _get_expected_outcome(decision, current_roas):
    """Get expected outcome description"""
    outcomes = {
        "pause": "Stop losses, prepare for restructure",
        "scale": f"Increase profitable returns (target: {current_roas * 1.2:.1f}x ROAS)",
        "clone": "Expand reach while maintaining performance",
        "edit_creative": "Improve CTR and engagement (target: 1.5%+ CTR)",
        "change_audience": "Reduce CPC, improve conversion rate",
        "revise_offer": "Increase conversion rate (target: 2%+)",
        "optimize_budget": "Improve cost efficiency",
        "wait": "Gather sufficient data for informed decisions"
    }
    return outcomes.get(decision, "Improve overall performance")




