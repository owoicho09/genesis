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
from agent.tools.rag_setup import setup_product_rag_chroma
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI


load_dotenv()
campaign_db_name = os.getenv("CHROMA_DB_BASE_PATH_CAMPAIGN", "./chroma_campaign_db")
db_name = os.getenv("CHROMA_DB_BASE_PATH", "./chroma_db")
persist_dir = db_name  # or another env variable if you want
MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")
#openai = OpenAI()





#fine tuning
@tool
def generate_campaign_summary(campaign_id: str) -> str:
    """
    Generates an intelligent summary of a campaign using LLM analysis.
    Fetches the campaign by ID and composes a natural language summary.
    Also sends this summary to your email.
    """
    campaign = agent_models.Campaign.objects.filter(campaign_id=campaign_id).first()
    if not campaign:
        return "❌ Campaign not found."

    content = f"""
    You are a campaign analyst. Here's the campaign data:

    Headline: {campaign.headline}
    Platform: {campaign.platform}
    Objective: {campaign.objective}
    Start Date: {campaign.start_date}
    End Date: {campaign.end_date}
    Budget: ${campaign.budget}
    Audience: {json.dumps(campaign.audience, indent=2)}
    Result Metrics: {json.dumps(campaign.result_metrics, indent=2)}

    Provide a short, intelligent summary of this campaign.
    Mention objective, audience focus, timing, and performance.
    Be clear and concise.
    """

    result = llm.invoke(content)
    return result


@tool
def generate_product_adcopy_and_headline_cta(campaign_id: str) -> str:
    """
    Fetches campaign data by campaign_id from the database.
    Generates compelling ad copy and headline for a product using LLM.
    Returns a dictionary with "headline","cta", and "ad_copy" or error.
    """
    campaign = agent_models.Campaign.objects.filter(campaign_id=campaign_id).first()
    product = campaign.product
    print('----',product.name)
    if not product:
        return {"error": "Product not found."}

    system_prompt = """
    You are a world-class ad copywriter. Learn from previous underperforming copies and improve them.
    Your job is to write a high-converting ad headline, short persuasive ad copy (under 50 words), and a sharp CTA.
    Use the product's name, description, use cases, and benefits.
    Always hit a key pain point or goal relevant to the product’s audience.

    Return ONLY valid JSON in this format:
    {
      "headline": "...",
      "ad_copy": "...",
      "cta": "..."
    }
    """

    content = f"""
    Product: {product.name}
    Description: {product.description}
    Use Cases: {product.useCases}
    Benefits: {product.benefits}
    Previous Ad Copy: {campaign.ad_copy}
    Previous Headline: {campaign.headline}
    Previous CTA: {campaign.cta}
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content}
    ]

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        raw = response.choices[0].message.content
        return json.loads(re.sub(r"```json|```", "", raw).strip())
    except Exception as e:
        return {"error": str(e)}


