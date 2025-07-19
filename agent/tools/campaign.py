from agent import models as agent_models
from django.utils import timezone
from datetime import timedelta
from datetime import timezone as dt_timezone, timedelta
from django.utils import timezone
import os
import glob
from dotenv import load_dotenv
# imports for langchain, plotly and Chroma
from agent.tools.system_prompt import analyze_system_prompt
from openai import OpenAI
from facebook_business.adobjects.campaign import Campaign
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




load_dotenv()
db_name = os.getenv("CHROMA_DB_BASE_PATH", "./chroma_db")
persist_dir = db_name  # or another env variable if you want
MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")

openai = OpenAI()
openai_api_key = os.getenv('OPENAI_API_KEY')
anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
google_api_key = os.getenv('GOOGLE_API_KEY')
META_ACCESS_TOKEN =  os.getenv('META_ACCESS_TOKEN')


#@tool

def create_campaign_from_analysis(product_data):
    """
    Create a campaign object from LLM analysis + DB enrich.
    Assigns relevant creatives based on platform and ad type.
    """
    try:


        print("🔍 Processing campaign for product:", product_data.get("product_id"))

        # 📦 Fetch product instance
        product = agent_models.Product.objects.get(product_id=product_data["product_id"])

        # 🎯 Extract values
        platforms = product_data.get("platforms", [])
        publisher_platforms = product_data.get("publisher_platforms", [])
        facebook_positions = product_data.get("facebook_positions", [])
        instagram_positions = product_data.get("instagram_positions", [])
        ad_types = product_data.get("ad_types", [])

        audience = product_data.get("audience", {})
        behaviors = product_data.get("behaviors", [])

        platform = platforms[0] if platforms else "facebook"
        all_platform = platforms[1:] if len(platforms) > 1 else []

        ad_type = ad_types[0] if ad_types else "image"
        ad_type_subtypes = ad_types[1:] if len(ad_types) > 1 else []

        ad_copy = product_data.get("ad_copy", "")
        headline = product_data.get("headline", "")
        cta = product_data.get("cta", "Learn More")

        price = product_data.get("price") or getattr(product, "price", 10)
        budget = product_data.get("budget") or getattr(product, "budget", 10)

        OBJECTIVE_MAP = {
            "brand_awareness": "OUTCOME_AWARENESS",
            "reach": "REACH",
            "traffic": "OUTCOME_TRAFFIC",
            "engagement": "OUTCOME_ENGAGEMENT",
            "app_installs": "OUTCOME_APP_PROMOTION",
            "video_views": "VIDEO_VIEWS",
            "lead_generation": "OUTCOME_LEADS",
            "messages": "MESSAGES",
            "conversions": "CONVERSIONS",
            "catalog_sales": "PRODUCT_CATALOG_SALES",
            "store_traffic": "STORE_VISITS",
        }

        objective = product_data.get("objective", "conversions").lower()
        meta_objective = OBJECTIVE_MAP.get(objective, "CONVERSIONS")

        # Dates
        start_dt = timezone.now().astimezone(dt_timezone.utc)
        end_dt = start_dt + timedelta(days=5)
        start_date = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_date = end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        # ✅ Create campaign
        campaign = agent_models.Campaign.objects.create(
            product=product,
            platform=platform,
            all_platform=all_platform,
            audience=audience,
            ad_type=ad_type,
            ad_type_subtypes=ad_type_subtypes,
            ad_copy=ad_copy,
            headline=headline,
            cta=cta,
            objective=meta_objective,
            product_price=price,
            budget=budget,
            start_date=start_date,
            end_date=end_date,
            is_active=False,
            status='inactive'
        )
        print("✅ Campaign created successfully:", campaign.campaign_id)

        # 🔍 Attach creative
        matched_creative = agent_models.AdsCreatives.objects.filter(
            product=product,
            is_active=True
        ).first()

        if matched_creative:
            campaign.creatives.set([matched_creative])
            campaign.campaign_files = [{
                "type": ad_type,
                "image_hash": matched_creative.file_hash or "",
                "url": matched_creative.file_url.url if matched_creative.file_url else "",
                "headline": headline,
                "cta": cta,
                "ad_copy": ad_copy
            }]
            matched_creative.is_active = False
            matched_creative.save()
            campaign.save()

            campaign_payload = {
                "campaign_name": f"{product.name} - {platform}",
                "campaign_id": campaign.campaign_id,
                "headline": headline,
                "platform": platform,
                "publisher_platforms": publisher_platforms,
                "facebook_positions": facebook_positions,
                "instagram_positions": instagram_positions,
                "objective": meta_objective,
                "ad_type": ad_type,
                "budget": str(budget),
                "audience": audience,
                "behaviors": behaviors,
                "creatives": campaign.campaign_files,
                "creatives_attached": 1,
                "start_date": campaign.start_date,
                "end_time": campaign.end_date
            }

            print("📦 Final Campaign Payload:", campaign_payload)
            return campaign_payload

        else:
            print("⚠️ No matching creatives found.")
            return {
                "message": "⚠️ Campaign created, but no creatives found.",
                "campaign_id": campaign.campaign_id,
                "payload": None,
                "creatives_attached": 0
            }

    except agent_models.Product.DoesNotExist:
        return {"error": "❌ Product not found in database."}
    except Exception as e:
        print("❌ Campaign creation failed:", str(e))
        return {"error": str(e)}

