from agent import models as agent_models
from django.utils import timezone as django_timezone
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
def fetch_campaign_metrics(meta_campaign_id: str) -> dict:
    """
    Fetch performance metrics for a Meta campaign and update the Campaign model.
    Returns a structured dictionary of metrics or an error object.
    """

    url = f"{BASE_URL}/{meta_campaign_id}/insights"
    params = {
        'access_token': ACCESS_TOKEN,
        'fields': ','.join([
            'campaign_name',
            'impressions',
            'reach',
            'frequency',
            'clicks',
            'ctr',
            'cpc',
            'spend',
            'inline_link_clicks',
            'actions',
            'purchase_roas'
        ]),
        'date_preset': 'today'  # change to 'last_7d' or 'yesterday' for better signal
    }

    resp = requests.get(url, params=params)

    if resp.status_code != 200:
        print("❌ Meta API Error:")
        print(resp.json())
        return {"error": resp.json()}

    data = resp.json().get('data', [])
    if not data:
        return {"error": "No data returned from Meta."}

    row = data[0]

    # Handle ROAS value safely
    spend = float(row.get("spend", 0))

    # ⬇️ Get local revenue from DB
    try:
        campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)
        purchases = int(campaign.purchases or 0)  # ← read from your model
        start_date = campaign.created_at  # Already a datetime object
        now = datetime.now(timezone.utc)
        days_running = max(1, (now - start_date).days)
        revenue = float(campaign.revenue or 0)
    except agent_models.Campaign.DoesNotExist:
        revenue = 0
        purchases = 0

    # 💡 Calculate ROAS
    roas = round(revenue / spend, 2) if spend > 0 and revenue > 0 else 0.0



    # Final structured result
    metrics = {
        "meta_campaign_id": meta_campaign_id,
        "campaign_name": row.get("campaign_name", ""),
        "impressions": int(row.get("impressions", 0)),
        "reach": int(row.get("reach", 0)),
        "frequency": float(row.get("frequency", 0)),
        "clicks": int(row.get("inline_link_clicks", row.get("clicks", 0))),
        "ctr": float(row.get("ctr", 0)),
        "cpc": float(row.get("cpc", 0)),
        "spend": float(row.get("spend", 0)),
        "purchases": purchases,
        "purchase_roas": roas,
        "profit": round(revenue - spend, 2),
        "days_running":days_running

    }

    # ⏱️ Update campaign summary in your Django model
    try:
        campaign.result_metrics = metrics
        campaign.purchase_roas = roas
        campaign.updated_at = timezone.now()
        campaign.save()
    except agent_models.Campaign.DoesNotExist:
        print(f"⚠️ Campaign with ID {meta_campaign_id} not found in DB.")

    return metrics



@tool
def fetch_all_active_campaign_metrics() -> list[dict]:
    """
    Fetch metrics for all active Meta campaigns in the DB.
    Returns a list of metric dictionaries (one per campaign).
    """
    metrics_list = []
    active_campaigns = agent_models.Campaign.objects.filter(status="active")

    for campaign in active_campaigns:
        meta_campaign_id = campaign.meta_campaign_id
        metrics = fetch_campaign_metrics(meta_campaign_id)

        if "error" not in metrics:
            metrics_list.append(metrics)
        else:
            print(f"⚠️ Skipping campaign {meta_campaign_id}: {metrics['error']}")

    return metrics_list
























