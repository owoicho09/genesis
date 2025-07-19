from agent import models as agent_models
import re
import json

import os
import glob
from dotenv import load_dotenv
# imports for langchain, plotly and Chroma
from agent.tools.system_prompt import analyze_system_prompt

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
from openai import OpenAI
from agent.tools.rag_setup import setup_product_rag_chroma,embed_campaign
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI


load_dotenv()
campaign_db_name = os.getenv("CHROMA_DB_BASE_PATH_CAMPAIGN", "./chroma_campaign_db")
db_name = os.getenv("CHROMA_DB_BASE_PATH", "./chroma_db")
persist_dir = db_name  # or another env variable if you want
MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")





@tool
def refresh_all_vector_dbs(dummy: str = "") -> dict:
    """
    Rebuilds both the product and campaign vector databases.
    Useful after bulk updates to product/campaign data.
    """
    try:
        print("🔁 Refreshing Product Vector DB...")
        setup_product_rag_chroma("")  # Since it accepts a dummy product_name arg

        print("🔁 Refreshing Campaign Vector DB...")
        embed_campaign()  # No args

        return {
            "status": "success",
            "message": "Both product and campaign vector DBs refreshed successfully."
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }



#@tool
def update_campaign_fields(data: dict) -> dict:
    """
    Update campaign fields in DB only for provided values.
    Skips fields that are missing or None.

    Expects a dict like:
    {
        "campaign_id": "WEuzJYg",
        "budget": 50,
        "headline": "New Headline",
        "ad_copy": "Fresh ad copy",
        "description": "Ad description"
    }
    """
    try:
        campaign_id = data.get("campaign_id")
        if not campaign_id:
            return {"error": "campaign_id is required."}

        campaign = Campaign.objects.get(campaign_id=campaign_id)

        updatable_fields = ["budget", "headline", "ad_copy", "description"]
        updated_fields = {}

        for field in updatable_fields:
            if field in data and data[field] is not None:
                setattr(campaign, field, data[field])
                updated_fields[field] = data[field]

        if updated_fields:
            campaign.save()

        return {
            "status": "success",
            "updated_fields": updated_fields or "No fields updated"
        }

    except Exception as e:
        return {"error": str(e)}




