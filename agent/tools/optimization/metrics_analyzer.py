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
def analyze_campaign_metrics(metrics: dict) -> dict:
    """
    Analyze Meta campaign metrics with adaptive scoring and smart flagging.
    Provides actionable insights for campaign optimization and send a brief email summary.
    """
    from agent.tools.optimization.scheduler import send_campaign_alert

    # ----------------------------
    # ✅ Extract Raw Metrics
    # ----------------------------
    meta_campaign_id = metrics.get('meta_campaign_id')
    ctr = metrics.get("ctr", 0)
    roas = metrics.get("purchase_roas", 0)
    cpc = metrics.get("cpc", 0)
    spend = metrics.get("spend", 0)
    conversions = metrics.get("purchases", 0)
    frequency = metrics.get("frequency", 0)

    # Additional metrics for better analysis
    impressions = metrics.get("impressions", 0)
    clicks = metrics.get("clicks", 0)
    cpm = metrics.get("cpm", 0)
    campaign_objective = metrics.get("objective", "conversions")  # Default to conversions
    days_running = metrics.get("days_running", 1)  # How long campaign has been active

    # ----------------------------
    # ✅ Calculate Derived Metrics
    # ----------------------------
    # Proper conversion rate calculation
    conversion_rate = (conversions / clicks * 100) if clicks > 0 else 0

    # Cost per conversion
    cost_per_conversion = spend / conversions if conversions > 0 else 0

    # Daily spend rate
    daily_spend = spend / days_running if days_running > 0 else spend

    # Get campaign object (assuming this exists in your system)
    try:
        campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)
    except:
        campaign = None

    # ----------------------------
    # Initialize Containers
    # ----------------------------
    recommendations = []
    flags = []
    score = 50  # Start with neutral score, not 0

    # ----------------------------
    # 1. CTR Analysis — Creative Effectiveness
    # ----------------------------
    # Industry benchmark: 0.9-1.5% is average, 2%+ is excellent
    if ctr < 0.5:
        flags.append("critically_low_ctr")
        score -= 25
        recommendations.append(
            "🔴 CTR critically low (<0.5%). Creative needs immediate overhaul - test new hooks, visuals, and copy.")
    elif ctr < 0.9:
        flags.append("low_ctr")
        score -= 15
        recommendations.append("🟡 CTR below industry average. Test more engaging creatives and stronger hooks.")
    elif ctr < 1.5:
        score += 5
        recommendations.append("🟢 CTR is decent. Room for improvement with creative optimization.")
    elif ctr < 2.5:
        score += 15
        recommendations.append("🟢 Strong CTR! Your creative is resonating well with the audience.")
    else:
        score += 20
        recommendations.append("🟢 Excellent CTR! Your creative is highly engaging.")

    # Creative fatigue detection
    if ctr < 1.0 and frequency > 1.5:
        flags.append("creative_fatigue")
        recommendations.append("🟡 Low CTR + high frequency indicates creative fatigue. Refresh ads immediately.")

    # ----------------------------
    # 2. ROAS Analysis — Profitability
    # ----------------------------
    # Adjust thresholds based on business model (typically 3:1 minimum for profitability)
    if roas == 0:
        if spend > 15:  # More reasonable threshold
            flags.append("zero_roas_high_spend")
            score -= 30
            recommendations.append("🔴 No ROAS after significant spend. Pause and investigate conversion tracking.")
        else:
            flags.append("zero_roas_early")
            score -= 10
            recommendations.append("🟡 No ROAS yet - normal for new campaigns. Monitor closely.")
    elif roas < 2.0:
        flags.append("unprofitable_roas")
        score -= 20
        recommendations.append("🔴 ROAS below breakeven. Optimize targeting, landing page, or pause campaign.")
    elif roas < 3.0:
        flags.append("marginal_roas")
        score += 0
        recommendations.append("🟡 ROAS near breakeven. Optimize for better profitability.")
    elif roas < 5.0:
        score += 20
        recommendations.append("🟢 Good ROAS! Campaign is profitable.")
    else:
        score += 30
        recommendations.append("🟢 Excellent ROAS! Scale this campaign carefully.")

    # ----------------------------
    # 3. CPC Analysis — Cost Efficiency
    # ----------------------------
    # CPC thresholds vary by industry, but these are more realistic
    if cpc > 2.0:
        flags.append("high_cpc")
        score -= 15
        recommendations.append("🔴 CPC too high. Refine targeting, improve quality score, or test new audiences.")
    elif cpc > 1.0:
        flags.append("moderate_cpc")
        score -= 5
        recommendations.append("🟡 CPC is moderate. Look for optimization opportunities.")
    elif cpc > 0.5:
        score += 5
        recommendations.append("🟢 CPC is reasonable for your market.")
    else:
        score += 10
        recommendations.append("🟢 Excellent CPC! Very cost-efficient traffic.")

    # ----------------------------
    # 4. Frequency Analysis — Ad Fatigue
    # ----------------------------
    if frequency >= 3.5:
        flags.append("severe_ad_fatigue")
        score -= 25
        recommendations.append("🔴 Severe ad fatigue (3.5+ frequency). Immediately refresh creative or expand audience.")
    elif frequency >= 2.0:
        flags.append("ad_fatigue")
        score -= 15
        recommendations.append("🟡 High frequency detected. Plan creative refresh or audience expansion.")
    elif frequency >= 1.5:
        score += 5
        recommendations.append("🟢 Frequency is optimal - good reach without oversaturation.")
    elif frequency < 1.2:
        if spend > 20:  # Only flag if significant spend
            flags.append("low_frequency_high_spend")
            score -= 5
            recommendations.append("🟡 Low frequency despite high spend. Audience might be too broad.")
        else:
            score += 10
            recommendations.append("🟢 Efficient frequency - reaching fresh audiences.")

    # ----------------------------
    # 5. Conversion Analysis — Funnel Health
    # ----------------------------
    if conversions == 0:
        if spend > 15:
            flags.append("no_conversions_significant_spend")
            score -= 35
            recommendations.append(
                "🔴 No conversions after $15+ spend. Check conversion tracking, landing page, and offer.")
        elif spend > 10:
            flags.append("no_conversions_moderate_spend")
            score -= 20
            recommendations.append("🟡 No conversions yet. Monitor closely and check funnel optimization.")
        else:
            score -= 5
            recommendations.append("🟡 Early stage - allow time for conversion data.")
    else:
        # Analyze conversion rate (clicks to conversions)
        if conversion_rate < 1.0:
            flags.append("low_conversion_rate")
            score -= 15
            recommendations.append("🔴 Low conversion rate (<1%). Optimize landing page, pricing, or offer.")
        elif conversion_rate < 2.0:
            score += 0
            recommendations.append("🟡 Conversion rate needs improvement. Test landing page elements.")
        elif conversion_rate < 5.0:
            score += 10
            recommendations.append("🟢 Good conversion rate. Consider scaling.")
        else:
            score += 20
            recommendations.append("🟢 Excellent conversion rate! Scale with confidence.")

    # ----------------------------
    # 6. Spend Velocity Analysis
    # ----------------------------
    if daily_spend > 15:
        if roas < 3.0:
            flags.append("high_spend_low_return")
            score -= 10
            recommendations.append("🟡 High daily spend with low ROAS. Consider reducing budget until optimized.")
    elif daily_spend < 10:
        if cpc < 0.5:  # If CPC is low but spend is low, might need more budget
            recommendations.append("🟢 Low spend with efficient CPC. Consider increasing budget.")

    # ----------------------------
    # 7. Overall Campaign Health Indicators
    # ----------------------------
    # Good metrics together
    if ctr > 2.5 and roas > 3.0 and conversion_rate > 2.5:
        score += 15
        recommendations.append("🟢 🎯 Campaign is firing on all cylinders! Consider scaling.")
        flags.append("scaling_opportunity")

    # Bad metrics together (compounding issues)
    if ctr < 1.0 and roas < 2.0 and frequency > 2.5:
        score -= 15
        flags.append("multiple_issues")
        recommendations.append("🔴 Multiple performance issues detected. Pause and restructure campaign.")

    # ----------------------------
    # Normalize Score: Clamp 0–100
    # ----------------------------
    score = max(0, min(100, score))

    # ----------------------------
    # Final Status Assignment
    # ----------------------------
    if score < 30:
        status = "critical"
        status_emoji = "🔴"
    elif score < 50:
        status = "underperforming"
        status_emoji = "🟡"
    elif score < 75:
        status = "performing"
        status_emoji = "🟢"
    else:
        status = "excellent"
        status_emoji = "🟢"

    # ----------------------------
    # Priority Action Items
    # ----------------------------
    priority_actions = []

    if "critically_low_ctr" in flags or "severe_ad_fatigue" in flags:
        priority_actions.append("URGENT: Refresh creative immediately")

    if "zero_roas_high_spend" in flags or "no_conversions_significant_spend" in flags:
        priority_actions.append("URGENT: Check conversion tracking and landing page")

    if "scaling_opportunity" in flags:
        priority_actions.append("OPPORTUNITY: Scale budget by 20-30%")

    # ----------------------------
    # Return Comprehensive Analysis
    # ----------------------------
    analysis = {
        "meta_campaign_id": meta_campaign_id,
        "status": status,
        "status_emoji": status_emoji,
        "score": score,
        "metrics": {
            "roas": roas,
            "ctr": ctr,
            "cpc": cpc,
            "conversion_rate": round(conversion_rate, 2),
            "cost_per_conversion": round(cost_per_conversion, 2),
            "frequency": frequency,
            "daily_spend": round(daily_spend, 2)
        },
        "flags": flags,
        "recommendations": recommendations,
        "priority_actions": priority_actions,
        "analysis_summary": f"{status_emoji} Campaign is {status} with {score}/100 health score"
    }
    send_campaign_alert(flags,recommendations)
    return analysis


@tool
def analyze_all_active_campaign_metrics(metrics_list: List[dict]) -> List[dict]:
    """
    Analyze multiple campaign metrics and return analysis results for each campaign.
    """
    results = []
    for metrics in metrics_list:
        try:
            analysis = analyze_campaign_metrics(metrics)
            results.append(analysis)
        except Exception as e:
            results.append({"meta_campaign_id": metrics.get("meta_campaign_id"), "error": str(e)})
    return results
