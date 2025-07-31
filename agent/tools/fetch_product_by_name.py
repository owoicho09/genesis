
import re
import json

import os
import glob,sys
from dotenv import load_dotenv
# imports for langchain, plotly and Chroma
#from agent.tools.utils.parser import clean_and_parse_usecase_output  # your parser

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI

from typing import Dict
from openai import OpenAI



# Set the base path to the root of your Django project (where manage.py lives)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, PROJECT_ROOT)

# Tell Django where to find settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Set up Django
import django
django.setup()

from agent import models as agent_models
load_dotenv()
campaign_db_name = os.getenv("CHROMA_DB_BASE_PATH_CAMPAIGN", "./chroma_campaign_db")
db_name = os.getenv("CHROMA_DB_BASE_PATH", "./chroma_db")
persist_dir = db_name  # or another env variable if you want
MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")
openai_api_key= os.getenv("OPENAI_API_KEY")  # or hardcode as 'sk-...'
openai = OpenAI(api_key=openai_api_key)

def fetch_product_by_name(product_name: str) -> Dict:
    """
    Semantically fetch a product from the vector database by name.
    Returns the full product metadata: title, description, features, etc.
    which can be passed into other tools.
    """
    embeddings = OpenAIEmbeddings()

    # Load vector store
    vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)

    # Search for most similar product
    retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 1})
    results = retriever.invoke(product_name)
    print('check',results[0].page_content)
    if results:
        metadata = results[0].metadata
        output = {
            "title": metadata.get("name", ""),
            "description": results[0].page_content,
            "product_id": metadata.get("product_id", ""),
            "price": metadata.get("price", 0.0),
            "useCases": metadata.get("useCases", []),
            "benefits": metadata.get("benefits", "General"),
        }
        return output

        # Return error in case no product is found
    else:
        return {
            "error": f"No product found matching '{product_name}'. Please check the name or try again."
        }



# ✅ Tool 2: Fetch a campaign by name (semantic search)
def fetch_campaign_by_name(query: str) -> dict:
    """
    Performs a semantic search in the campaign vector DB to find the best-matching campaign by name or description.
    Returns campaign metadata and key details.
    """
    embeddings = OpenAIEmbeddings()
    campaign_vectorstore = Chroma(
        persist_directory=campaign_db_name,  # must match path used in embed_campaign()
        embedding_function=embeddings
    )

    retriever = campaign_vectorstore.as_retriever(search_type="similarity",search_kwargs={"k": 1})
    results = retriever.invoke(query)

    if not results:
        return {"error": "No matching campaign found"}

    best_match = results[0]

    # ✅ Log and return as dict
    print("\n🔍 Best match found:\n", best_match.page_content)
    print("\n📎 Metadata:\n", best_match.metadata)
    metadata = best_match.metadata

    return {
        "content": best_match.page_content,
        "status": metadata.get('status'),
        "campaign_product_name":metadat.get('campaign_product_name'),
        "campaign_id": metadata.get('campaign_id'),
        "meta_campaign_id": metadata.get('meta_campaign_id'),

    }



def clean_and_parse_usecase_output(raw_output: str):
    # Clean markdown if wrapped
    raw_output = re.sub(r"```json|```", "", raw_output).strip()
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        return {}

def product_usecases_benefits_generator() -> str:
    """
    Generates and saves use cases and benefits for each product if not already present.
    """
    products = agent_models.Product.objects.all()

    for product in products:
        print(f"🔍 Generating use cases for: {product.name}")

        prompt = f"""
You are a smart assistant that identifies use cases and benefits of digital products.

Return JSON for the product "{product.name}":

{{
  "useCases": ["Short use case 1", "Short use case 2"],
  "benefits": ["Short benefit 1", "Short benefit 2"]
}}

Only return raw JSON. No markdown or explanations.

Product description: {product.description or ""}
        """

        try:
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9,
                max_tokens=300
            )

            content = response.choices[0].message.content
            parsed = clean_and_parse_usecase_output(content)

            if "useCases" in parsed and "benefits" in parsed:
                if not product.useCases and not product.benefits:
                    product.useCases = parsed["useCases"]
                    product.benefits = parsed["benefits"]
                    product.save()
                    print(f"✅ Saved for {product.name}")
                else:
                    print(f"ℹ️ Skipped (already exists): {product.name}")
            else:
                print(f"⚠️ Invalid response for {product.name}: {content}")

        except Exception as e:
            print(f"❌ Error generating for {product.name}: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    product_usecases_benefits_generator()
