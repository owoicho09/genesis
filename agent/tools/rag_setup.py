from agent import models as agent_models

import os
import glob
from dotenv import load_dotenv
# imports for langchain, plotly and Chroma
from agent.tools.system_prompt import analyze_system_prompt
from langchain.tools import tool
from shutil import rmtree

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
from langchain_community.vectorstores.utils import filter_complex_metadata
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate



load_dotenv()
db_name = os.getenv("CHROMA_DB_BASE_PATH", "./chroma_db")
campaign_db_name = os.getenv("CHROMA_DB_BASE_PATH_CAMPAIGN", "./chroma_campaign_db")

persist_dir = db_name  # or another env variable if you want
MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")

@tool
def setup_product_rag_chroma(product_name: str) -> str:
    """Creates a Chroma vectorstore from all products for semantic search and retrieval.
        It loads product data, formats it, embeds it, and stores it for use in RAG pipelines."""
    products = agent_models.Product.objects.all()
    docs = []

    for product in products:
        # ✅ Extract and safely transform product fields
        tags = list(product.tags.values_list('name', flat=True))
        category = product.category.title if product.category else None
        features = product.features if product.features else []
        useCases = product.useCases if product.useCases else []
        benefits = product.benefits if product.benefits else []

        price = product.price if product.price else None
        features_str = ", ".join(features) if isinstance(features, list) else str(features)

        use_cases_str = ", ".join(useCases) if isinstance(useCases, list) else str(useCases)
        benefits_str = ", ".join(benefits) if isinstance(benefits, list) else str(benefits)

        # ✅ Compose document content for embedding
        content = (
            f"Name: {product.name}\n"
            f"Description: {product.description or ''}\n"
            f"useCases: {use_cases_str}\n"
            f"benefits: {benefits_str}\n"
        )

        # ✅ Add document with flat metadata (avoids Chroma metadata errors)
        metadata = {
            "id": product.id,
            "name": product.name,
            "product_id": product.product_id,
            "price": float(product.price),
            "is_active": product.is_active,
            "date": product.date.isoformat(),

        }

        # ✅ Clean metadata using LangChain utility to ensure all values are simple types
        doc = Document(page_content=content, metadata=metadata)

        # ✅ Filter complex metadata
        #doc = filter_complex_metadata(doc)

        docs.append(doc)

    # 2. Split documents into chunks
    splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=100)
    split_docs = splitter.split_documents(docs)
    print(f'✅ Document split successful..........{split_docs[0]}')

    print(f"Total number of chunks: {len(split_docs)}")
    print(f"Document types found: {set(doc.metadata['name'] for doc in split_docs)}")

    # 3. Generate IDs per chunk
    ids = [f"{doc.metadata['id']}_{i}" for i, doc in enumerate(split_docs)]

    # 4. Setup embedding model
    embeddings = OpenAIEmbeddings()

    # 5. Persist to ChromaDB
    if os.path.exists(db_name):  # ✅ db_name must be defined at module level or passed
        vectorstore = Chroma(persist_directory=persist_dir, embedding_function=embeddings)

        existing = set()
        if hasattr(vectorstore, 'get'):
            all_data = vectorstore.get(include=['metadatas'])  # ✅ 'ids' is invalid include
            existing = set(all_data.get('ids', []))  # Safe fallback

        new_docs = []
        new_ids = []
        for doc, doc_id in zip(split_docs, ids):
            if doc_id not in existing:
                new_docs.append(doc)
                new_ids.append(doc_id)

        if new_docs:
            vectorstore.add_documents(new_docs, ids=new_ids)  # ✅ Only add non-duplicate docs
    else:
        vectorstore = Chroma.from_documents(
            split_docs,
            embedding=embeddings,
            persist_directory=persist_dir,
            ids=ids
        )

    print(f"Vectorstore created with {vectorstore._collection.count()} documents")
    print('✅ Vectorstore created and saved successfully.')
    collection = vectorstore._collection
    count = collection.count()
    #print(f"There are {count:,} vectors in the vector store")
    sample_embedding = collection.get(limit=1, include=["embeddings"])["embeddings"][0]
    dimensions = len(sample_embedding)
    #print(f"There are {count:,} vectors with {dimensions:,} dimensions in the vector store")
    return vectorstore


#@tool
def embed_campaign():
    """
    Embed all campaigns into Chroma vector database with campaign metadata.
    Performs a full rebuild each time.
    """
    campaigns = agent_models.Campaign.objects.all()
    docs = []

    for campaign in campaigns:
        content = (
            f"Campaign for: {campaign.product.name}\n"
            f"Platform: {campaign.platform}\n"
            f"Headline: {campaign.headline}\n"
            f"Budget: ${campaign.budget}\n"
            f"Start Date: {campaign.start_date}\n"
            f"End Date: {campaign.end_date}\n"
            f"Objective: {campaign.objective}\n"
            f"Result Metrics: {campaign.result_metrics}"
        )

        metadata = {
            "campaign_id": str(campaign.campaign_id),
            "campaign_product_name": str(campaign.product.name),
            "meta_campaign_id": campaign.meta_campaign_id,
            "status": campaign.status,
        }

        docs.append(Document(page_content=content, metadata=metadata))
        print('docs---->',docs)
    # Split all documents together
    splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=100)
    split_docs = splitter.split_documents(docs)

    print(f'✅ Split into {len(split_docs)} chunks.')

    # Generate unique IDs
    ids = [f"{doc.metadata['campaign_id']}_{i}" for i, doc in enumerate(split_docs)]

    # Rebuild Chroma DB
    if os.path.exists(campaign_db_name):
        rmtree(campaign_db_name)
        print(f"🧹 Wiped old vector DB at {campaign_db_name}")

    embeddings = OpenAIEmbeddings()

    campaign_vectorstore = Chroma.from_documents(
        split_docs,
        embedding=embeddings,
        persist_directory=campaign_db_name,
        ids=ids
    )

    print(f"✅ campaign_vectorstore now has {campaign_vectorstore._collection.count()} documents.")
    return campaign_vectorstore




def fetch_product_from_prompt(user_prompt: str):
    vs = setup_product_rag_chroma()
    llm = ChatOpenAI(temperature=0.7, model_name=MODEL)

    retriever = vs.as_retriever(search_kwargs={"k": 5})
    qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=retriever,
            chain_type="stuff",
            chain_type_kwargs={"prompt": analyzer_system_prompt }
            )
    result = qa_chain.invoke({"query": user_prompt})
    gpt_output = result.get("result", "⚠️ No answer returned.")
    print("🧠 GPT Answer:", gpt_output)
    return gpt_output
