from agent.tools.rag_setup import setup_product_rag_chroma
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI
from agent.tools.system_prompt import analyze_system_prompt
from agent.tools.optimization.campaign_log import get_product_specific_logs
from agent import models as agent_models
import os
from dotenv import load_dotenv
import json
from langchain.tools import tool
from openai import OpenAI
import re

load_dotenv()
db_name = os.getenv("CHROMA_DB_BASE_PATH", "./chroma_db")
persist_dir = db_name  # or another env variable if you want
MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")

llm = ChatOpenAI(model=MODEL, temperature=0)
openai_api_key = os.getenv('OPENAI_API_KEY')
anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
google_api_key = os.getenv('GOOGLE_API_KEY')
META_ACCESS_TOKEN =  os.getenv('META_ACCESS_TOKEN')


@tool
def analyze_product_audience(product_data: dict)->dict:
    """
       Analyze the product (from fetch_product_by_name) and generate a full campaign setup:
       - Ideal platforms
       - Target audience
       - Ad formats
       - Campaign description
       - Headline and CTA
       Returns structured JSON for use in downstream tools.
       """

    print("🔍 product_data keys:", product_data.keys())
    print("📦 product_data full:", product_data)
    product_id = product_data.get("product_id")
    product = agent_models.Product.objects.get(product_id=product_id)
    logs = agent_models.OptimizationLog.objects.filter(product=product)

    if logs:
        past_logs_prompt = "\n\n".join([
            f"""📊 Campaign Snapshot:
    Platform: {log['platform']} | Ad Type: {log['ad_type']}
    Audience: {', '.join(log['audience'].get('interests', []))}
    Budget: ${log['budget']} | Price: ${log['product_price']}
    📈 ROAS: {log.get('roas')} | CVR: {log.get('conversion_rate')}
    🎯 Action Taken: {log['action_taken']} → Reason: {log['reason']}
    """
            for log in logs[:5]
        ])
    else:
        past_logs_prompt = "No past campaign logs available for this product."

    #add
    prompt = f"""
    You are a sniper-level Meta Ads strategist and AI campaign analyst.

    Your job is to extract high-converting Meta ad targeting from this product, which includes structured segment data with pain points, tools used, and buyer behavior patterns.

    📦 Product: {product_data['title']}
    🧠 Description (with embedded segment data If segment details are missing,
     intelligently infer high-intent audiences from the use cases and benefits.):
    {product_data['description']}

    🛠 Use Cases:
    {json.dumps(product_data.get("useCases", []), indent=2)}

    💡 Benefits:
    {json.dumps(product_data.get("benefits", []), indent=2)}

    📁 Past Campaign History:
    {past_logs_prompt if logs else ""}

    ---
    
    🎯 Generate a sniper-targeted Meta Ads campaign JSON that includes:
    
    - High-converting platform + placement recommendations
    - Precise audience targeting
    - Smart creative suggestions

    {{
      "product": "{product_data['title']}",
      "product_id": "{product_data['product_id']}",

      "platforms": ["/* list the most relevant Meta platforms (e.g., facebook, instagram) */"],
      "publisher_platforms": ["/* match platforms above */"],
    
      // ✅ Define the exact placements the ad should appear in:
     "facebook_positions": ["feed", "story"],  // ✅ Facebook only allows 'feed' and 'story'
     "instagram_positions": ["feed", "explore", "reels", "story"]  // ✅ Always include at least 'feed' and 'explore'    
      // Available placements for reference:
      // facebook → feed, story
      // instagram → story, reels, explore
      
      "ad_types": [/* image or video */ ],
      "objective": "conversions",
      "audience": {{
        "interests": ["provide exactly 15 high-intent interests related to the product"],
        
        // ✅ Use Meta-compatible terminology that maps to real interests.
        // 🎯 Replace conceptual or niche roles with practical, Meta-recognizable terms.
        
        If your interest suggestion is too niche or vague,
        map it to a Meta-compatible version using this format:

        ❌ "{{concept}}" → ✅ "{{meta_interest_1}}" or "{{meta_interest_2}}"

        
        // Examples:
        // ❌ "Fitness solopreneur" → ✅ "Personal trainer"
        // ❌ "Social video content creators" → ✅ "Instagram" or "Video editing"
        // ❌ "AI-powered content marketers" → ✅ "Content marketing" or "Artificial intelligence"
        // ❌ "Marketing-savvy gym owners" → ✅ "Fitness and wellness", "Digital marketing", or "Small business"
          // Use this format when mapping:
        // ❌ "{{vague}}" → ✅ "{{meta_interest_1}}", "{{meta_interest_2}}"
    
        "behaviors": [/* fill dynamically */ ],
        "demographics": {{
          "age_min": 25,
          "age_max": 45,
          "education_statuses": ["College grads"],
          "relationship_statuses": ["All"]
        }},
        "gender": "all"
      }},
      "creative_strategy": {{
     "headline": "Create a compelling, unique headline that highlights the product's main benefit or pain point.",
    "ad_copy": "Write persuasive ad copy tailored to the audience and product, avoiding repeated phrases.",
    "cta": "/* e.g. LEARN_MORE,SEE_MORE,BUY_NOW */" #select the best cta from the example
      }}
    }}
    ⚠️If fields like past logs or segment insights are not available,
     infer from the product title, use cases, and benefits.
      Your goal is to generate a Meta Ads campaign that targets the most likely high-intent
       buyers using expert insight.

    Only respond with valid JSON.
    """

    messages = [
        {"role": "system", "content": "You are an expert Meta ads strategist trained on thousands of campaigns. Your job is to translate product and audience intelligence into high-ROI targeting and ad strategy."},
        {"role": "user", "content": prompt}
    ]

    try:
        response = llm.invoke(prompt)
        raw_output = response.content.strip()
        cleaned = re.sub(r"```json|```", "", raw_output).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            return {
                "error": "❌ JSON parsing failed",
                "exception": str(e),
                "raw_output": raw_output
            }

    except Exception as e:
        return {"error": str(e)}



def fetch_product_from_prompt_analyzer(user_prompt: str):
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



