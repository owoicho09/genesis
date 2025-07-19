from agent.tools.optimization.campaign_analytics import generate_product_adcopy_and_headline_cta
from agent import models as agent_models
from django.utils import timezone
import requests
import json
import os
from typing import List
from copy import deepcopy

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





from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.ad import Ad
from django.db import transaction
import requests
import logging

logger = logging.getLogger(__name__)




load_dotenv()
db_name = os.getenv("CHROMA_DB_BASE_PATH", "./chroma_db")
persist_dir = db_name  # or another env variable if you want
MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")

import os
from langchain_openai import ChatOpenAI

print("MODEL:", MODEL)
print("API_KEY exists:", bool(os.getenv("OPENAI_API_KEY")))
print("Environment proxy vars:", {k: v for k, v in os.environ.items() if 'proxy' in k.lower()})

try:
    llm = ChatOpenAI(model=MODEL, temperature=0, api_key=os.getenv("OPENAI_API_KEY"))
    print("ChatOpenAI initialized successfully")
except Exception as e:
    print("Error:", e)
    print("Exception type:", type(e))


# 🔐 Your credentials
ad_account_id = os.getenv('fb_ad_account_id')
app_id = os.getenv('fb_app_id')
app_secret = os.getenv('fb_app_secret')
page_id = os.getenv('fb_page_id')



BASE_URL = "https://graph.facebook.com/v23.0"
ACCESS_TOKEN = os.getenv("SYSTEM_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("fb_ad_account_id")


@tool
def modify_campaign_from_decision(decision_data: dict) -> dict:
    """
    Takes the decision output and applies the appropriate modification to the campaign.
    Supports actions like: pause, scale, clone, edit_creative, change_audience, revise_offer, optimize_budget.
    """

    decision = decision_data.get("decision")
    meta_campaign_id = decision_data.get("meta_campaign_id")
    reason = decision_data.get("reason")
    priority = decision_data.get("priority")
    expected_outcome = decision_data.get("expected_outcome")

    # Fetch campaign object
    try:
        campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)
    except agent_models.Campaign.DoesNotExist:
        return {"status": "error", "message": f"Campaign {campaign_id} not found."}

    # Dispatch to action handler
    if decision == "pause":
        return pause_campaign(meta_campaign_id, reason) #✅✅✅
    elif decision == "scale":
        return scale_campaign(meta_campaign_id, decision_data)#✅✅✅
    elif decision == "clone":
        return clone_campaign(meta_campaign_id, decision_data)  #✅✅✅
    elif decision == "edit_creative":
        return refresh_creative(decision_data)  #✅✅✅
    elif decision == "change_audience":
        return update_audience_targeting(decision_data)  #✅✅✅
    elif decision == "revise_offer":
        return revise_offer_logic(decision_data)  #✅✅✅
    elif decision == "optimize_budget":
        return optimize_campaign_budget(decision_data) #✅✅✅
    elif decision == "wait":
        return {"status": "waiting", "message": "Campaign under observation. No action taken yet."}

    return {"status": "unhandled", "message": f"Unknown decision: {decision}"}

@tool
def modify_all_active_campaign_metrics(decision_list: List[dict]) -> List[dict]:
    """
    Applies campaign modifications for a list of decision outputs.
    """
    results = []
    for decision in decision_list:
        result = modify_campaign_from_decision(decision)
        results.append({
            "meta_campaign_id": decision.get("meta_campaign_id"),
            "decision": decision.get("decision"),
            "result": result
        })
    return results



@tool
def pause_campaign(decision_data: Dict) -> dict:
    """
    Pauses a Meta campaign via API using the campaign ID in decision_data.
    """
    meta_campaign_id = decision_data.get("meta_campaign_id")
    reason = decision_data.get("reason")


    url = f"{BASE_URL}/{meta_campaign_id}"
    payload = {
        "status": "PAUSED",
        "access_token": ACCESS_TOKEN
    }

    try:
        resp = requests.post(url, data=payload)
        resp.raise_for_status()
        # Update the Campaign database accodingly
        campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)
        campaign.status = 'paused'
        campaign.save()
        # 1. Create the log object first
        log = agent_models.OptimizationLog.objects.create(
            campaign=campaign,
            product=campaign.product,
            action=decision_data.get("action"),
            reason=decision_data.get("reason"),
            metrics_snapshot=decision_data.get("metrics_summary", {})
        )
        # 2. Add the new creative to the ManyToMany field
        log.creative_used.add(new_creative)
        # 3. (Optional) Add a note
        log.notes = decision_data.get("recommendations")
        log.save()
        return {
            "action": "pause",
            "status": "executed",
            "campaign_id": campaign_id,
            "response": resp.json(),
            "message": f"Campaign paused. Reason: {reason}"

        }
    except Exception as e:
        return {
            "action": "pause",
            "status": "failed",
            "error": str(e),
            "campaign_id": campaign_id
        }



@tool
def scale_campaign(decision_data: Dict = None) -> Dict:
    """
    Increases or decreases a Meta campaign’s ad set budget using ROAS and metrics.
    """
    try:
        # Extract ROAS from decision data
        metrics = decision_data.get("metrics_summary", {}) if decision_data else {}
        current_roas = metrics.get("roas", 0)

        # 🎯 Determine scale % based on ROAS
        if current_roas >= 5.0:
            scale_percent = 50
        elif current_roas >= 4.0:
            scale_percent = 35
        elif current_roas >= 3.0:
            scale_percent = 25
        else:
            scale_percent = 20

        # 🔍 Fetch adset ID and current budget
        adset_url = f"{BASE_URL}/{meta_campaign_id}?fields=adsets.limit(1){{id,daily_budget}}&access_token={ACCESS_TOKEN}"
        adset_resp = requests.get(adset_url)
        adset_resp.raise_for_status()
        adsets = adset_resp.json().get("adsets", {}).get("data", [])

        if not adsets:
            return {
                "status": "failed",
                "action": "scale",
                "meta_campaign_id": meta_campaign_id,
                "error": "No ad sets found."
            }

        adset = adsets[0]
        adset_id = adset["id"]
        current_budget = int(adset.get("daily_budget", 0))

        if current_budget <= 0:
            return {
                "status": "failed",
                "action": "scale",
                "meta_campaign_id": meta_campaign_id,
                "error": "Invalid or missing daily budget on ad set."
            }

        # 💰 Calculate new budget
        new_budget = int(current_budget * (1 + scale_percent / 100))

        # 🔧 Send update to Meta API
        budget_url = f"{BASE_URL}/{adset_id}"
        payload = {
            "daily_budget": new_budget,
            "access_token": ACCESS_TOKEN
        }
        budget_resp = requests.post(budget_url, data=payload)
        budget_resp.raise_for_status()
        meta_campaign_id = decision_data.get("meta_campaign_id")
        campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)
        # 1. Create the log object first
        log = agent_models.OptimizationLog.objects.create(
            campaign=campaign,
            product=campaign.product,
            action=decision_data.get("action"),
            reason=decision_data.get("reason"),
            metrics_snapshot=decision_data.get("metrics_summary", {})
        )
        # 2. Add the new creative to the ManyToMany field
        log.creative_used.add(new_creative)
        # 3. (Optional) Add a note
        log.notes = decision_data.get("recommendations")
        log.save()

        return {
            "status": "success",
            "action": "scale",
            "meta_campaign_id": meta_campaign_id,
            "adset_id": adset_id,
            "scale_percent": scale_percent,
            "old_budget": current_budget,
            "new_budget": new_budget,
            "reason": f"Scaled by {scale_percent}% due to ROAS: {current_roas:.1f}x",
            "response": budget_resp.json()
        }

    except Exception as e:
        return {
            "status": "failed",
            "action": "scale",
            "meta_campaign_id": meta_campaign_id,
            "error": str(e),
            "fallback": "Manual review or retry recommended."
        }


@tool
def clone_campaign(decision_data: Dict = None) -> Dict:
    """
    Clones a Meta campaign with timestamp suffix and optional variations from decision data.
    """
    try:
        meta_campaign_id = decision_data.get("meta_campaign_id")
        original = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)

        # 🎯 Create a unique suffix to identify the clone
        suffix = f"Clone_{meta_campaign_id}_{datetime.now().strftime('%m%d')}"

        # 🔁 Clone campaign via API
        url = f"{BASE_URL}/{meta_campaign_id}/copies"
        payload = {
            "access_token": ACCESS_TOKEN,
            "deep_copy": True,
            "rename_options": {
                "rename_strategy": "APPEND_SUFFIX",
                "rename_suffix": suffix
            },
            "status_option": "INHERITED"  # Start with same status as original
        }

        response = requests.post(url, json=payload)
        response.raise_for_status()
        clone_data = response.json()

        # ✅ Extract new campaign ID from Meta response
        new_campaign_id = clone_data.get("copied_campaign_id")
        new_campaign = agent_models.Campaign.objects.create(
            product=original.product,
            platform=original.platform,
            all_platform=original.all_platform,
            audience=original.audience,
            ad_type=original.ad_type,
            ad_type_subtypes=original.ad_type_subtypes,
            ad_copy=original.ad_copy,
            headline=original.headline,
            cta=original.cta,
            objective=original.objective,
            product_price=original.product_price,
            budget=original.budget,
            meta_campaign_id=new_campaign_id,
            start_date=datetime.now(),
            is_active=True,
            status='inactive'
        )
        print('✅ Campaign created successfully.', campaign.status)
        print('new campaign -->',new_campaign.meta_campaign_id)
        # 4. Copy creatives if any
        creatives = original.creatives.all()
        if creatives.exists():
            new_campaign.creatives.set(creatives)

        # 5. Copy campaign_files
        if original.campaign_files:
            new_campaign.campaign_files = deepcopy(original.campaign_files)
            new_campaign.save()




        # 🛠 Optional: Apply variations (creative, audience, etc.)
        #variation_result = apply_clone_variations(new_campaign_id, decision_data)

        # 1. Create the log object first
        log = agent_models.OptimizationLog.objects.create(
            campaign=original,
            product=original.product,
            action=decision_data.get("action"),
            reason=decision_data.get("reason"),
            metrics_snapshot=decision_data.get("metrics_summary", {})
        )
        # 2. Add the new creative to the ManyToMany field
        log.creative_used.add(new_creative)
        # 3. (Optional) Add a note
        log.notes = decision_data.get("recommendations")
        log.save()
        return {
            "status": "success",
            "action": "clone",
            "original_campaign_id": meta_campaign_id,
            "new_campaign_id": new_meta_campaign_id,
            "variations_applied": variation_result,
            "response": clone_data
        }


    except Exception as e:
        return {

            "status": "failed",
            "action": "clone",
            "campaign_id": meta_campaign_id,
            "error": str(e),
            "fallback": "Manual campaign duplication recommended"

        }




@tool
def refresh_creative(decision_data: Dict):
    """
    Refreshes a Meta campaign’s creative: deactivates current, selects new, generates copy, and launches updated ad.
    """
    meta_campaign_id = decision_data.get("meta_campaign_id")

    if not meta_campaign_id:
        return {"status": "failed", "error": "meta_campaign_id is required"}

    try:
        campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)

        # Validate required fields
        if not campaign.meta_adset_id:
            return {
                "status": "failed",
                "error": "Campaign missing meta_adset_id",
                "meta_campaign_id": meta_campaign_id
            }

        # 1. Find current and new creative
        current_creative = campaign.creatives.filter(is_active=True).first()
        new_creative = agent_models.AdsCreatives.objects.filter(
            product=campaign.product,
            is_active=True
        ).exclude(id=current_creative.id if current_creative else None).first()

        if not new_creative:
            return {
                "status": "failed",
                "reason": "No new creatives available.",
                "meta_campaign_id": meta_campaign_id
            }

        # 2. Generate new ad copy/headline
        copy_result = generate_product_adcopy_and_headline(campaign.campaign_id) #Send a dict of past headline and ad_copy so the func can intelligently address the next headline
        if "error" in copy_result:
            return {
                "status": "failed",
                "error": copy_result["error"],
                "meta_campaign_id": meta_campaign_id
            }

        headline = copy_result.get("headline") or new_creative.headline or campaign.headline
        ad_copy = copy_result.get("ad_copy") or new_creative.ad_copy or campaign.ad_copy
        cta = copy_result.get("cta") or new_creative.cta or campaign.cta
        #update database with new ad creatives
        with transaction.atomic():
            if current_creative:
                current_creative.is_active = False
                current_creative.save()

            campaign.creatives.set([new_creative])
            campaign.headline = headline
            campaign.ad_copy = ad_copy
            campaign.campaign_files = [{
                "type": new_creative.creative_type,
                "image_hash": new_creative.file_hash,
                "url": new_creative.file_url.url if hasattr(new_creative.file_url, 'url') else new_creative.file_url,
                "headline": headline,
                "cta": cta,
                "ad_copy": ad_copy
            }]
            campaign.save()

            # 1. Create the log object first
            log = agent_models.OptimizationLog.objects.create(
                campaign=campaign,
                product=campaign.product,
                action="edit_creative",
                reason=decision_data.get("reason"),
                metrics_snapshot=decision_data.get("metrics_summary", {})
            )
            # 2. Add the new creative to the ManyToMany field
            log.creative_used.add(new_creative)
            # 3. (Optional) Add a note
            log.notes = decision_data.get("recommendations")
            log.save()
        from agent.tools.launch_campaign import ad_creative

        # 3. Create new creative on Meta first
        adset_payload = {"meta_campaign_id": meta_campaign_id}
        meta_creative_id, headline_1 = ad_creative(adset_payload)

        if not meta_creative_id:
            return {
                "status": "failed",
                "error": "Failed to create Meta creative",
                "meta_campaign_id": meta_campaign_id
            }

        # 4. Pause old ad
        old_ad_id = _pause_old_ad(campaign.meta_adset_id)

        # 5. Create new ad
        new_ad_id = _create_new_ad(campaign.meta_adset_id, meta_creative_id, headline)

        if not new_ad_id:
            return {
                "status": "failed",
                "error": "Failed to create new ad",
                "meta_campaign_id": meta_campaign_id
            }

        # 6. Update database only after Meta operations succeed

        return {
            "status": "success",
            "action": "edit_creative",
            "meta_campaign_id": meta_campaign_id,
            "old_ad_id": old_ad_id,
            "new_creative_id": new_creative.creative_id,
            "meta_creative_id": meta_creative_id,
            "new_ad_id": new_ad_id,
            "headline": headline,
            "ad_copy": ad_copy,
            "reason": decision_data.get("reason"),
            "next_review": decision_data.get("next_review"),
            "expected_outcome": decision_data.get("expected_outcome")
        }

    except agent_models.Campaign.DoesNotExist:
        return {
            "status": "failed",
            "error": "Campaign not found",
            "meta_campaign_id": meta_campaign_id
        }
    except Exception as e:
        logger.error(f"Creative refresh failed for {meta_campaign_id}: {str(e)}")
        return {
            "status": "failed",
            "error": str(e),
            "meta_campaign_id": meta_campaign_id,
            "fallback": "Manual refresh required"
        }


def _pause_old_ad(meta_adset_id):
    """Pause the active ad in the adset"""
    try:
        url = f"{BASE_URL}/{meta_adset_id}/ads"
        params = {"access_token": ACCESS_TOKEN, "fields": "id,name,status"}
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        for ad in response.json().get("data", []):
            if ad["status"] == "ACTIVE":
                pause_url = f"{BASE_URL}/{ad['id']}"
                pause_resp = requests.post(
                    pause_url,
                    params={"access_token": ACCESS_TOKEN},
                    json={"status": "PAUSED"},
                    timeout=30
                )
                pause_resp.raise_for_status()
                logger.info(f"Paused old ad: {ad['id']}")
                return ad["id"]
    except Exception as e:
        logger.warning(f"Failed to pause old ad: {str(e)}")
    return None


def _create_new_ad(meta_adset_id, meta_creative_id, headline):
    """Create new ad with the creative"""
    try:
        payload = {
            "name": headline,
            "adset_id": meta_adset_id,
            "creative": {"creative_id": meta_creative_id},
            "status": "ACTIVE"
        }
        url = f"{BASE_URL}/act_{AD_ACCOUNT_ID}/ads"
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        if "id" in data:
            logger.info(f"Created new ad: {data['id']}")
            return data["id"]
        else:
            logger.error(f"Ad creation response missing ID: {data}")
    except Exception as e:
        logger.error(f"Failed to create new ad: {str(e)}")
    return None





@tool
def update_audience_targeting(decision_data: Dict):
    """
    Updates a Meta campaign's audience using LLM analysis and refreshed interest IDs.

    """
    meta_campaign_id = decision_data.get("meta_campaign_id")
    try:
        campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)
        adset_id = campaign.meta_adset_id

        if not adset_id:
            return {"status": "failed", "error": "meta_adset_id missing"}

        # 1. Re-analyze audience using LLM
        product = campaign.product
        prompt = f"""
        You are a well informed online marketing ads expert, use previous data to make better decision.

        Your task is to generate a better-performing audience for this product, based on the previous audience that underperformed.

        ---
        Product:
        Name: {product.name}
        Description: {product.description}
        Benefits: {product.benefits}
        Use Cases: {product.useCases}

        Previous Targeting:
        - Interests: {", ".join(campaign.audience.get("interests", []))}
        - Age Range: {campaign.audience.get("age_min", "")}–{campaign.audience.get("age_max", "")}
        - Gender: {campaign.audience.get("gender", "")}

        Why Refresh:
        Reason: {decision_data.get("reason")}
        Recommendations: {", ".join(decision_data.get("recommendations", []))}

        ---
        Respond with ONLY valid JSON in this format:

        {{
          "interests": ["..."],
          "age_min": ...,
          "age_max": ...,
          "gender": "male" | "female" | "all"
        }}
        """

        # Use LangChain LLM
        try:
            response_text = llm.invoke(prompt).strip()

            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1].rsplit("\n", 1)[0]

            result = json.loads(response_text)
        except Exception as err:
            return {"status": "failed", "error": f"Invalid LLM response: {err}"}


        interests = result.get("interests", [])
        age_min = result.get("age_min", 18)
        age_max = result.get("age_max", 65)
        gender = result.get("gender", "all")

        # Fix: Basic validation
        if not interests or len(interests) == 0:
            return {"status": "failed", "error": "No interests provided by LLM"}
        from agent.tools.launch_campaign import ad_creative, fetch_interests
        # 2. Fetch Meta interest IDs
        interest_ids = fetch_interests(interests)

        # Fix: Check if we got enough valid interests
        if not interest_ids or len(interest_ids) < 2:
            return {"status": "failed", "error": "Too few valid interests found"}

        targeting = {
            "age_min": age_min,
            "age_max": age_max,
            "genders": [1] if gender == "male" else [2] if gender == "female" else [],
            "interests": interest_ids
        }

        # 3. Update AdSet targeting on Meta
        update_url = f"{BASE_URL}/{adset_id}"
        response = requests.post(
            update_url,
            params={"access_token": ACCESS_TOKEN},
            json={"targeting": targeting}
        )
        response.raise_for_status()

        # 4. Save new audience in DB
        campaign.audience = {
            "interests": [interest["name"] for interest in interest_ids],
            "age_min": age_min,
            "age_max": age_max,
            "gender": gender
        }
        campaign.save()

        # 5. Log optimization
        log = agent_models.OptimizationLog.objects.create(
            campaign=campaign,
            product=product,
            action=decision_data.get("action"),
            reason=decision_data.get("reason"),
            metrics_snapshot=decision_data.get("metrics_summary", {})
        )
        log.notes = {
            "previous_audience": campaign.audience,
            "recommendations": decision_data.get("recommendations")
        }
        log.save()

        return {
            "status": "success",
            "meta_campaign_id": meta_campaign_id,
            "adset_id": adset_id,
            "audience": campaign.audience,
            "next_review": decision_data.get("next_review"),
            "expected_outcome": decision_data.get("expected_outcome")
        }

    except Exception as e:
        return {
            "status": "failed",
            "meta_campaign_id": meta_campaign_id,
            "error": str(e)
        }




@tool
def revise_offer_logic(decision_data: Dict):
    """
    Human-assist: surfaces key info & structured suggestions for revising an underperforming offer.
    Doesn't auto-apply. Used for human review or manual testing.
    """
    meta_campaign_id = decision_data.get("meta_campaign_id")
    try:
        campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)
        product = campaign.product

        # Gather key signals
        ctr = decision_data["metrics_summary"].get("ctr", 0)
        conversion_rate = decision_data["metrics_summary"].get("conversion_rate", 0)
        roas = decision_data["metrics_summary"].get("roas", 0)
        reason = decision_data.get("reason", "Low conversion performance")
        recommendations = decision_data.get("recommendations", [])

        # Generate offer revision assistant block
        structured_template = {
            "product_name": product.name,
            "current_price": product.price,
            "current_value_prop": getattr(product, "value_proposition", campaign.headline),
            "engagement_metrics": {
                "CTR (%)": f"{ctr:.2f}",
                "Conversion Rate (%)": f"{conversion_rate:.2f}",
                "ROAS": roas
            },
            "reason_for_offer_review": reason,
            "llm_recommendations": recommendations,
            "human_revision_template": {
                "suggested_price": "[Your new price here]",
                "new_offer_bonus": "[Add bonus/extra here]",
                "urgency_or_timer_hook": "[Add scarcity angle]",
                "value_messaging_update": "[Rewrite the pitch or hook]",
                "landing_page_tip": "[Suggest tweaks to boost trust or CTA]"
            }
        }

        # Log the optimization request
        log = agent_models.OptimizationLog.objects.create(
            campaign=campaign,
            product=product,
            action="revise_offer",
            reason=reason,
            metrics_snapshot=decision_data.get("metrics_summary", {})
        )
        log.notes = recommendations
        log.save()

        return {
            "status": "human_assist",
            "meta_campaign_id": meta_campaign_id,
            "action": "revise_offer",
            "assist_payload": structured_template,
            "next_review": decision_data.get("next_review"),
            "expected_outcome": decision_data.get("expected_outcome")
        }

    except agent_models.Campaign.DoesNotExist:
        return {"status": "failed", "error": "Campaign not found", "meta_campaign_id": meta_campaign_id}
    except Exception as e:
        return {"status": "failed", "error": str(e), "meta_campaign_id": meta_campaign_id}






@tool
def optimize_campaign_budget(decision_data: Dict, config: Dict = None):

    """
    Adjusts campaign budget based on ROAS performance with configurable thresholds.
    Supports scale up, scale down, or maintain actions with safety limits.

    """
    # Default configuration
    default_config = {
        'min_budget': 10.0,
        'max_budget': 500.0,
        'min_change': 1.0,
        'thresholds': {
            'high_roas': 3.0,
            'low_roas': 1.0,
            'scale_up': 1.3,
            'scale_down': 0.7,
            'scale_down_hard': 0.5
        }
    }
    config = {**default_config, **(config or {})}

    try:
        # Validation
        meta_campaign_id = decision_data.get("meta_campaign_id")
        campaign = agent_models.Campaign.objects.get(meta_campaign_id=meta_campaign_id)
        adset_id = campaign.meta_adset_id
        if not adset_id:
            return {"status": "failed", "error": "Missing meta_adset_id"}

        metrics = decision_data.get("metrics_summary", {})
        roas = float(metrics.get("roas", 0))
        current_budget = float(campaign.budget or 0)

        if current_budget <= 0:
            return {"status": "failed", "error": "Invalid current budget"}

        if roas <= 0:
            return {"status": "failed", "error": "Invalid ROAS data"}

        # Determine scaling action
        thresholds = config['thresholds']
        if roas >= thresholds['high_roas']:
            action = "scale_up"
            factor = thresholds['scale_up']
        elif roas >= thresholds['low_roas']:
            action = "maintain"
            factor = 1.0
        else:
            action = "scale_down"
            factor = thresholds['scale_down_hard'] if roas < 0.5 else thresholds['scale_down']

        # Calculate new budget with limits
        new_budget = round(current_budget * factor, 2)
        new_budget = max(config['min_budget'], min(new_budget, config['max_budget']))

        # Skip if change is too small
        if abs(new_budget - current_budget) < config['min_change']:
            return {"status": "noop", "message": "Budget change below threshold"}

        # Update Meta (with basic retry)
        success = False
        for attempt in range(2):
            try:
                response = requests.post(
                    f"{BASE_URL}/{adset_id}",
                    params={"access_token": ACCESS_TOKEN},
                    json={"daily_budget": int(new_budget * 100)},
                    timeout=30
                )
                response.raise_for_status()
                success = True
                break
            except requests.RequestException as e:
                if attempt == 1:  # Last attempt
                    raise e
                time.sleep(1)

        if not success:
            return {"status": "failed", "error": "Meta API update failed"}

        # Update database
        campaign.budget = new_budget
        campaign.save()

        # Log optimization
        agent_models.OptimizationLog.objects.create(
            campaign=campaign,
            product=campaign.product,
            action="optimize_budget",
            reason=decision_data.get("reason", f"ROAS-based {action}"),
            metrics_snapshot=metrics,
            notes=f"ROAS: {roas:.2f}, Budget: ${current_budget:.2f} → ${new_budget:.2f}"
        )

        return {
            "status": "success",
            "old_budget": current_budget,
            "new_budget": new_budget,
            "action": action,
            "roas": roas
        }

    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "campaign_id": getattr(campaign, 'meta_campaign_id', 'unknown')
        }







