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
from agent.tools.optimization.scheduler import send_campaign_alert

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
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")


#@tool
def fetch_interests(interests: List[str]) -> List[Dict]:
    """
        Fetch interest IDs from Meta Marketing API given a list of interest names.
        Returns a list of dictionaries with 'id' and 'name'.
        """
    results = []
    for interest in interests:
        r = requests.get(
            "https://graph.facebook.com/v19.0/search",
            params={
                "q": interest,
                "type": "adinterest",
                "access_token": ACCESS_TOKEN
            }
        )
        data = r.json().get("data", [])
        if data:
            results.append({"id": data[0]["id"], "name": data[0]["name"]})
    print("🎯 Fetched Interest IDs:", results)
    return results

#@tool
def fetch_behaviors(behaviors: List[str], limit=25) -> List[Dict]:
    """
    Fetch Meta Ads targeting behavior IDs from the Graph API based on behavior names.

    Args:
        behaviors (list[str]): List of behavior keywords to search for.
        limit (int): Max results to return per behavior search (default: 25).

    Returns:
        List[dict]: Each dict contains id, name, and audience size bounds.
    """
    META_ACCESS_TOKEN = os.getenv('SYSTEM_ACCESS_TOKEN')
    results = []

    for behavior in behaviors:
        r = requests.get(
            "https://graph.facebook.com/v19.0/search",
            params={
                "q": behavior,
                "type": "adTargetingCategory",
                "class": "behaviors",
                "limit": limit,
                "access_token": META_ACCESS_TOKEN
            }
        )
        data = r.json().get("data", [])
        if data:
            behavior_data = data[0]  # Use the first match
            results.append({
                "id": behavior_data.get("id"),
                "name": behavior_data.get("name"),
                })

    return results

#@tool
def create_campaign_on_meta(campaign_payload):
    """
    Creates a campaign on Meta's ad platform using the given campaign dict.
    Also prepares ad set payload with targeting details (interest, gender, age, geo, behaviors).
    Returns the ad set payload and the created meta campaign ID.
    """
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"

    }

    META_OBJECTIVE_MAP = {
        "brand_awareness": "BRAND_AWARENESS",
        "reach": "REACH",
        "traffic": "OUTCOME_TRAFFIC",  # Replaced 'LINK_CLICKS'
        "engagement": "OUTCOME_ENGAGEMENT",  # Replaced 'POST_ENGAGEMENT'
        "app_installs": "OUTCOME_APP_PROMOTION",  # New version of APP_INSTALLS
        "video_views": "VIDEO_VIEWS",
        "lead_generation": "OUTCOME_LEADS",  # Replaced 'LEAD_GENERATION'
        "messages": "MESSAGES",
        "conversions": "OUTCOME_SALES",
        "catalog_sales": "PRODUCT_CATALOG_SALES",
        "store_traffic": "STORE_VISITS",
    }
    campaign_id = campaign_payload.get('campaign_id')
    campaign = agent_models.Campaign.objects.get(campaign_id=campaign_id)

    objective = campaign.objective
    if not objective:
        raise ValueError(f"❌ 'objective' is missing or None in payload: {campaign}")
    objective = objective.strip().lower()
    mapped_objective = META_OBJECTIVE_MAP[objective]

    # === 1. Create Campaign ===
    payload = {
        "name": campaign_payload["headline"],
        "objective": mapped_objective,
        "status": "PAUSED",
        "special_ad_categories": json.dumps([]),
    }

    campaign_url = f"{BASE_URL}/act_{AD_ACCOUNT_ID}/campaigns"
    campaign_response = requests.post(campaign_url, data=payload, headers=headers)
    campaign_data = campaign_response.json()
    print("🧱 Campaign Response:", campaign_data)

    if 'id' not in campaign_data:
        return {"error": "Campaign creation failed", "details": campaign_data}

    meta_campaign_id = campaign_data['id']
    campaign.meta_campaign_id = meta_campaign_id
    campaign.save()

    
    # === 2. Fetch Interest IDs ===
    raw_interests = campaign_payload["audience"].get("interests", [])
    interest_objs = fetch_interests(raw_interests)


    # === 3 Fetch behavior ids ==
    raw_behaviors = campaign_payload["audience"].get("behaviors", [])
    behavior_objs = fetch_behaviors(raw_behaviors)


    # === 3. Create Ad Set Payload ===
    targeting = {
        "age_min": campaign_payload["audience"]["demographics"]["age_min"],
        "age_max": 65,
        "genders": [1] if campaign_payload["audience"]["gender"] == 'male' else [2] if campaign_payload["audience"]["gender"] == 'female' else [],
        "geo_locations": {
            "countries": ["US", "GB", "CA","AU"],
            "location_types": ["home", "recent"]
        },
        "interests": interest_objs,
        "behaviors": behavior_objs,
        "publisher_platforms": campaign_payload.get("publisher_platforms", ["facebook", "instagram"]),
        "facebook_positions": ["feed", "story", "facebook_reels"],
        "instagram_positions": ["stream", "story", "reels", "explore"],
        "targeting_automation": {
            "advantage_audience": 0  # explicitly required
        }
    }

    adset_payload = {
        "name": f"AdSet for {campaign_payload['headline']}",
        "campaign_id": meta_campaign_id,
        "daily_budget": int(float(campaign_payload["budget"]) * 100),
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "REACH",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "start_time": campaign_payload.get("start_date") or datetime.now(timezone.utc).isoformat(),

        "creatives": campaign_payload['creatives'],
        "end_time": campaign_payload.get("end_time") or (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        "targeting": targeting,
        "status": "PAUSED"
    }
    print('--targeting--',targeting)
    print('--adset_payload--',adset_payload)

    return adset_payload

#@tool
def ads_set_meta(adset_payload):
    """
    Creates ad set and ad creative using the ad set payload.
    Requires campaign_id to be included.
    Returns the Meta ad set ID or error info.
    """
    if not adset_payload:
        return {"error": "Missing adset_payload in input"}

    meta_campaign_id = adset_payload.get('campaign_id')

    if "campaign_id" not in adset_payload:
        raise ValueError("❌ Missing 'meta_campaign_id' in ad set payload — required by Meta API.")
    campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    meta_payload = {k: v for k, v in adset_payload.items() if k != "creatives"}

    adset_url = f"{BASE_URL}/act_{AD_ACCOUNT_ID}/adsets"
    adset_response = requests.post(adset_url, json=meta_payload, headers=headers)
    adset_data = adset_response.json()
    print("🎯 Ad Set Response:", adset_data)

    if 'id' not in adset_data:
        return {"error": "AdSet creation failed", "details": adset_data}

    meta_adset_id = adset_data['id']
    campaign.meta_adset_id = meta_adset_id
    campaign.save()
    print('--Meta AdSet ID--', meta_adset_id)
    return {"meta_adset_id": meta_adset_id}



#@tool
def ad_creative(adset_payload):
    """
    Creates a Meta Ad Creative using the first creative linked to the campaign.
    Requires the campaign to have at least one creative with a valid image/video link.
    Returns the Meta creative ID if successful.
    """
    headers = {
        "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    page_id = os.getenv("fb_page_id")  # ensure this is loaded correctly
    meta_campaign_id = adset_payload.get('campaign_id')
    if not meta_campaign_id:
        return {"error": "meta_campaign_id not provided in adset_payload"}

        # Fetch campaign and creative data
    try:
        campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)
    except agent_models.Campaign.DoesNotExist:
        return {"error": "Campaign not found"}

    if not campaign.campaign_files or len(campaign.campaign_files) == 0:
        return {"error": "No creative file info in campaign.campaign_files"}

    creative_data = campaign.campaign_files[0]
    creative_type = creative_data.get("type")
    file_hash = creative_data.get("image_hash") or creative_data.get("video_id")
    file_url = creative_data.get("url") or ""
    headline = creative_data.get("headline") or campaign.headline or ""
    ad_copy = creative_data.get("ad_copy") or campaign.ad_copy or ""
    cta = creative_data.get("cta") or campaign.cta or "LEARN_MORE"

    # First upload the image to Meta to get its image hash
    if not file_hash:
        return {"error": "file_hash (image_hash/video_id) is missing in campaign_files"}

    if creative_type.lower() == "image":
        media_spec_key = "link_data"
        media_spec = {
            "image_hash": file_hash,
            "message": ad_copy,
            "name": headline,
            "link": campaign.product.url,  # ✅ actual destination URL
            "call_to_action": {
                "type": cta.upper(),
                "value": {
                    "link": campaign.product.url
                }
            }
        }
    elif creative_type.lower() == "video":
        media_spec_key = "link_data"  # ✅ still use link_data to allow redirection!
        media_spec = {
            "video_id": file_hash,
            "message": ad_copy,
            "name": headline,
            "link": campaign.product.url,
            "call_to_action": {
                "type": cta.upper(),
                "value": {
                    "link": campaign.product.url
                }
            }
        }

    else:
        return {"error": f"Unsupported creative type: {creative_type}"}

    creative_payload = {
        "name": f"Creative for {headline}",
        "object_story_spec": {
            "page_id": page_id,
            media_spec_key: media_spec
        }
    }

    creative_url = f"{BASE_URL}/act_{AD_ACCOUNT_ID}/adcreatives"
    creative_response = requests.post(creative_url, json=creative_payload, headers=headers)
    creative_data = creative_response.json()
    print("🎨 Creative Response:", creative_data)

    if 'id' not in creative_data:
        return {"error": "Creative creation failed", "details": creative_data}

    meta_creative_id = creative_data['id']
    print("✅ Returning new meta_creative_id:", meta_creative_id)

    campaign.meta_creative_id = meta_creative_id
    campaign.save()
    return meta_creative_id,headline


#@tool
def create_ad(headline, meta_adset_id=None, meta_creative_id=None):
    """
    Creates a Meta Ad by linking an existing Ad Set and Ad Creative.
    """
    print("🧠 Received creative ID:", meta_creative_id)

    url = f"{BASE_URL}/act_{AD_ACCOUNT_ID}/ads"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "name": headline,
        "adset_id": meta_adset_id,
        "creative": {
            "creative_id": meta_creative_id  # ✅ object, not JSON string
        },
        "status": "PAUSED"
    }

    print("📦 Ad Payload:", payload)
    from agent.tools.backdoor.optimization.scheduler import send_campaign_alert
    subject = "Campaign launced successfully on Meta💪"
    message = "Genesis Ai just launched a campaign"
    send_campaign_alert()
    response = requests.post(url, json=payload, headers=headers)
    print(response)
    print("📨 Ad API Response:", response.status_code, response.text)

    return response.json()

