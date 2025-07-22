from langchain_openai import ChatOpenAI


from langgraph.graph.message import add_messages
from langchain.output_parsers import StructuredOutputParser,PydanticOutputParser

from pydantic import BaseModel,Field
from langgraph.graph import StateGraph,END
from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import HumanMessage
from typing import TypedDict, Optional, Dict, Any


from agent.tools.rag_setup import *
from agent.tools.campaign import *
from agent.tools.launch_campaign import *
from agent.tools.analyze_product import *
from agent.tools.fetch_product_by_name import *
from agent.tools.product_manager import *
from agent.tools.ad_platform import *
from agent.tools.database_update import *
from agent.tools.utils.date_parser import *
from agent.tools.optimization.metric_fetcher import *
from agent.tools.optimization.metrics_analyzer import *
from agent.tools.optimization.decision_maker import *
from agent.tools.optimization.campaign_modifier import *
from agent.tools.optimization.campaign_analytics import *
from agent.tools.optimization.scheduler import *
from agent.tools.backdoor.email_compose.cold_outreach import *
from agent.tools.backdoor.email_compose.inbox_warmup import *
from agent.tools.backdoor.scraper import google_map_scraping,instagram_scraping
from agent.tools.utils.send_email_update import send_emails

from langchain.chat_models import init_chat_model
import json,os
from langchain.memory import ConversationBufferMemory
from django.urls import reverse
from django.conf import settings
from django.utils.html import escape
from django.core.mail import EmailMultiAlternatives


test_leads = [
    MockLead(email="michaelogaje033@gmail.com", username="coachmike", niche="fitness",
             bio="Helping people burn fat at home with zero equipment."),
    MockLead(email="kennkiyoshi@gmail.com", username="fitkenn", niche="fitness",
             bio="Helping people build muscle with zero equipment."),
    MockLead(email="owi.09.12.02@gmail.com", username="yogaowi", niche="fitness",
             bio="Helping people build stamina."),
    MockLead(email="unitorial111@gmail.com", username="yogaowi", niche="fitness",
             bio="Helping people select the best nutrition for bodybuilding"),

]

# === 1. SHARED STATE ===
class CampaignAgentState(TypedDict):
    user_input: str
    detected_intent: str  # e.g. "launch_campaign", "get_metrics", etc.
    product_name: Optional[str]
    budget: float
    campaign_id: Optional[str]
    date_range: Optional[str]  # e.g. "last_7_days"

    product_data: dict
    audience: dict
    adcopy: dict
    campaign: dict
    adset_payload: dict
    meta_adset_id: str
    meta_creative_id: str
    headline: str
    final_ad: dict

    batch_size: Optional[int] = 30
    delay_minutes: Optional[int] = 10
    niche: Optional[str]
    location: Optional[str]
    recipient_list: Optional[list]
    message: Optional[str] = ""
    result: Optional[str]  # ✅ Add this


# === 2. LLM SETUP ===
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# === 3. INTENT PARSER MODEL ===
class IntentSchema(BaseModel):
    detected_intent: str = Field(..., description="The type of action to perform")
    product_name: Optional[str] = ""
    budget: Optional[float] = 10.0
    campaign_id: Optional[str] = ""
    date_range: Optional[str] = "last_7_days"
    batch_size: Optional[int] = 30
    delay_minutes: Optional[int] = 10
    niche: Optional[str] = ""
    location: Optional[str] = ""
    recipient_list: Optional[list]
    message: Optional[str] = ""

parser = PydanticOutputParser(pydantic_object=IntentSchema)


def intent_node(state: CampaignAgentState) -> CampaignAgentState:
    print("🧠 Running: intent_node")
    user_input = state["user_input"]
    response = llm.invoke([
        HumanMessage(content=f"""
        Classify the user request and extract relevant fields.
        Return as JSON like:
        {{
          "detected_intent": "launch_campaign", "optimize_campaign", "get_metrics", "revise_offer", "summarize_campaign", "refresh_audience", "send_outreach", "send_email" ,"google_scrape", "instagram_scrape","warmup_emails"
         "product_name": "...",         // e.g. "Flyer Prompt Pack", "Marketing Toolkit", optional
          "budget": float (optional),
          "campaign_id": "...", 
          "date_range": "last_7_days" | "today" | null,
          "batch_size": 10,
          "delay_minutes": 10,
          "niche": "...",                 // e.g. "personal trainer", "yoga coach", etc
          "location": "...",
          "recipient_list": "[...]",
          "message": "..."
        }}
        User input: {user_input}
        """)
    ])
    try:
        parsed = parser.parse(response.content)
        print("✅ Parsed intent:", parsed)
        return {**state, **parsed.dict()}
    except Exception as e:
        print("❌ Failed to parse intent:", e)
        return {**state, "error": str(e)}


def fetch_product_node(state):
    print("📦 Running: fetch_product_node")
    try:
        product = fetch_product_by_name(state["product_name"])
        print("✅ Raw product fetched:", product.get("title"))

        # Try to extract JSON block from description
        if isinstance(product.get("description"), str):
            match = re.search(r'\{[\s\S]*\}', product["description"])
            if match:
                try:
                    parsed_json = json.loads(match.group())
                    product["parsed"] = parsed_json
                    print("✅ Parsed product description JSON")
                except Exception as e:
                    print("⚠️ Failed to parse product JSON from description:", e)
            else:
                print("⚠️ No JSON block found in description")

        return {**state, "product_data": product}
    except Exception as e:
        print("❌ Error in fetch_product_node:", e)
        return {**state, "error": str(e)}


def analyze_audience_node(state):
    print("🎯 Running: analyze_audience_node")
    try:
        parsed_product = state["product_data"].get("parsed", {})
        if not parsed_product:
            raise ValueError("Parsed product data is missing.")

        product_data = state["product_data"]
        print("🔍 product_data keys:", product_data.keys())
        audience = analyze_product_audience({"product_data": product_data})
        print("✅ Audience analysis complete",audience)
        return {**state, "audience": audience}
    except Exception as e:
        print("❌ Error in analyze_audience_node:", e)
        return {**state, "error": str(e)}


def generate_adcopy_node(state):
    print("✍️ Running: generate_adcopy_node")
    try:
        adcopy = generate_product_adcopy_and_headline_cta(state["campaign"]["campaign_id"])
        print("✅ Ad copy generated")
        return {**state, "adcopy": adcopy}
    except Exception as e:
        print("❌ Error in generate_adcopy_node:", e)
        return {**state, "error": str(e)}




def create_campaign_node(state):
    """
    Enhanced create_campaign_node with better error handling and data validation
    """
    print("🏗️ Running: create_campaign_node")
    try:
        audience_analysis = state.get("audience", {})
        creative = audience_analysis.get("creative_strategy", {})

        # ✅ Enhanced: Better data validation and defaults
        full_product_data = {
            "product_id": audience_analysis.get("product_id"),
            "platforms": audience_analysis.get("platforms", ["facebook"]),
            "publisher_platforms": audience_analysis.get("publisher_platforms", []),
            "facebook_positions": audience_analysis.get("facebook_positions", []),
            "instagram_positions": audience_analysis.get("instagram_positions", []),
            "ad_types": audience_analysis.get("ad_types", ["image"]),
            "objective": audience_analysis.get("objective", "conversions"),
            "audience": audience_analysis.get("audience", {}),
            "behaviors": audience_analysis.get("audience", {}).get("behaviors", []),
            "ad_copy": creative.get("ad_copy", ""),
            "headline": creative.get("headline", ""),
            "cta": creative.get("cta", "Learn More"),
            "budget": state.get("budget", 10.0),
            "price": state.get("price")  # ✅ Added price field
        }

        # ✅ Enhanced: Validate required fields
        if not full_product_data["product_id"]:
            raise ValueError("product_id is required")

        print(f"🔍 Processing campaign for product: {full_product_data['product_id']}")
        result = create_campaign_from_analysis(full_product_data)

        if "error" in result:
            print(f"❌ Campaign creation failed: {result['error']}")
            return {**state, "error": result["error"]}

        print("✅ Campaign object created successfully")
        return {**state, "campaign": result}

    except Exception as e:
        error_msg = f"❌ Error in create_campaign_node: {str(e)}"
        print(error_msg)
        return {**state, "error": error_msg}



def create_campaign_on_meta_node(state):
    print("📡 Running: create_campaign_on_meta_node")
    try:
        campaign_payload = state["campaign"]
        adset_payload = create_campaign_on_meta(campaign_payload)
        print("✅ Meta campaign + adset payload created")
        return {**state, "adset_payload": adset_payload}
    except Exception as e:
        print("❌ Error in create_campaign_on_meta_node:", e)
        return {**state, "error": str(e)}


def ads_set_meta_node(state):
    print("🧩 Running: ads_set_meta_node")
    try:
        adset_payload = state["adset_payload"]
        meta_adset_id = ads_set_meta(adset_payload)
        print("✅ Meta AdSet created:", meta_adset_id)
        return {**state, "meta_adset_id": meta_adset_id}
    except Exception as e:
        print("❌ Error in ads_set_meta_node:", e)
        return {**state, "error": str(e)}


def ad_creative_node(state):
    print("🎨 Running: ad_creative_node")
    try:
        adset_payload = state["adset_payload"]
        meta_creative_id, headline = ad_creative(adset_payload)
        print("✅ Creative created:", meta_creative_id)
        return {**state, "meta_creative_id": meta_creative_id, "headline": headline}
    except Exception as e:
        print("❌ Error in ad_creative_node:", e)
        return {**state, "error": str(e)}


def create_ad_node(state):
    print("🚀 Running: create_ad_node")
    try:
        # Use creative ID from previous node (fresh from Meta)
        print("📥 DEBUG: meta_creative_id in state = ", state.get("meta_creative_id"))
        meta_adset_id = state["meta_adset_id"]
        if isinstance(meta_adset_id, dict) and "meta_adset_id" in meta_adset_id:
            meta_adset_id = meta_adset_id["meta_adset_id"]  # ✅ Extract actual string
        ad = create_ad(
            headline=state["headline"],
            meta_adset_id=meta_adset_id,
            meta_creative_id=state["meta_creative_id"]
        )
        print("📥 DEBUG: Full state keys = ", state.keys())

        if "id" in ad:
            # ✅ Optionally update DB here only after success
            campaign_id = state["campaign"]["campaign_id"]
            if campaign_id:
                try:
                    campaign = agent_models.Campaign.objects.get(campaign_id=campaign_id)
                    campaign.status = 'active'
                    campaign.meta_ad_id = ad["id"]
                    campaign.save()
                    print("✅ Campaign status updated to active")
                except Exception as e:
                    print("⚠️ Warning: Couldn't update campaign status:", e)

            print("✅ Final ad launched:", ad["id"])
            return {**state, "final_ad": ad}
        else:
            print("❌ Ad creation failed:", ad)
            return {**state, "error": ad}

    except Exception as e:
        print("❌ Error in create_ad_node:", e)
        return {**state, "error": str(e)}

#🧠 Optional nodes you can later plug in

def summarize_campaign_node(state: Dict[str, Any]) -> Dict:
    try:
        result = generate_campaign_summary(state["campaign"]["campaign_id"])
        return {**state, "summary": result}
    except Exception as e:
        return {**state, "error": str(e)}






def fetch_metrics_node(state: Dict[str, Any]) -> Dict:
    try:
        adset_payload = state["adset_payload"]
        result = fetch_campaign_metrics(adset_payload["meta_campaign_id"])
        return {**state, "metrics": result}
    except Exception as e:
        return {**state, "error": str(e)}


def metrics_analyzer_node(state: Dict[str, Any]) -> Dict:
    try:
        analysis = analyze_campaign_metrics(state["metrics"])
        return {**state, "analysis": analysis}
    except Exception as e:
        return {**state, "error": str(e)}



def decide_campaign_action_node(state: Dict[str, Any]) -> Dict:
    try:
        decision_data = decide_campaign_action(state["metrics"],state["analysis"])
        return {**state, "decision_data": decision_data}
    except Exception as e:
        return {**state, "error": str(e)}



def modify_campaign_from_decision_node(state: Dict[str, Any]) -> Dict:
    try:
        modification = modify_campaign_from_decision(state["decision_data"])
        return {**state, "modification": modification}
    except Exception as e:
        return {**state, "error": str(e)}





def optimize_campaign_node(state: Dict[str, Any]) -> Dict:
    metrics = state["metrics"]
    decision = decide_campaign_action(metrics)
    modified = modify_campaign_from_decision(decision)
    return {**state, "optimization_decision": decision, "updated_campaign": modified}



# ==== # BACKDOOR INTELLIGENCE =============== #
# langgraph_nodes.py
os

def email_outreach_node(state: dict) -> dict:
    """LangGraph node to trigger cold email outreach"""
    try:
        smtp_configs = load_smtp_configs()
        openai_api_key = os.getenv("OPENAI_API_KEY")
        manager = EmailOutreachManager(openai_api_key, smtp_configs)

        niche = state.get("niche", "fitness coach")
        batch_size = int(state.get("batch_size", 30))
        delay_minutes = int(state.get("delay_minutes", 10))

        results = manager.send_batch_outreach(
            niche=niche,
            batch_size=batch_size,
            delay_minutes=delay_minutes
        )

        return {**state, "outreach_results": results}
    except Exception as e:
        return {**state, "error": str(e)}


#Test outreach
def warmup_email_node(state: dict) -> dict:
    setup_django()

    try:
        smtp_configs = load_smtp_configs()
        manager = EmailWarmUpManager(smtp_configs)

        # Filter valid leads
        valid_leads = filter_valid_leads(test_leads)

        if not valid_leads:
            print("No valid leads found. Please check your test data.")
            return

        print(f"Starting warmup for {len(valid_leads)} leads...")
        manager.send_warmup_batch(valid_leads, leads_per_inbox=2, delay_minutes=1)
        print("Warmup process completed!")

    except Exception as e:
        print(f"Error during warmup: {e}")


def send_email_node(state: dict) -> dict:
    setup_django()
    print("📨 Running: send_email_node")  # Add this log

    try:
        recipient_list = state.get("recipient_list", ["michaelogaje033@gmail.com"])
        message = state.get("message", "owoicho is a genius")

        subject = "Genesis Ai"
        for email in recipient_list:
            # Create tracking pixel
            pixel_url = settings.SITE_URL + reverse("agent:email_open", args=[email])
            tracking_pixel = f'<img src="{escape(pixel_url)}" width="1" height="1" style="display:none;" />'

            html_message =f"""
                            <html>
                              <body>
                                <p>{message}</p>
                                <br>
                                {tracking_pixel}
                              </body>
                            </html>
                        """
            msg = EmailMultiAlternatives(subject, message, settings.FROM_EMAIL, [email])
            msg.attach_alternative(html_message, "text/html")
            msg.send()

        summary = f"✅ Email sent to {', '.join(recipient_list)}"
        return {**state, "result": summary}

    except Exception as e:
        print(f"❌ Error in send_email_node: {e}")
        return {**state, "result": f"❌ Failed to send email: {str(e)}"}


def google_maps_scraping_node(state: dict) -> dict:
    """LangGraph node to run Google Maps scraping."""
    try:
        niche = state.get("niche", "fitness coach")
        location = state.get("location", "atlanta")
        result = google_map_scraping(niche,location)
        return {**state, "google_scraping_result": result}
    except Exception as e:
        return {**state, "error": f"Google Maps Scraping Error: {str(e)}"}


def instagram_scraping_node(state: dict) -> dict:
    """LangGraph node to run Instagram scraping."""
    try:
        niche = state.get("niche", "fitness")
        result = instagram_scraping(niche)
        return {**state, "instagram_scraping_result": result}
    except Exception as e:
        return {**state, "error": f"Instagram Scraping Error: {str(e)}"}


# === 6. BUILD THE GRAPH ===
graph = StateGraph(CampaignAgentState)

# Add all nodes
graph.add_node("intent_node", intent_node)
graph.add_node("fetch_product", fetch_product_node)
graph.add_node("analyze_audience", analyze_audience_node)
graph.add_node("create_campaign", create_campaign_node)
graph.add_node("generate_adcopy", generate_adcopy_node)
graph.add_node("create_campaign_on_meta", create_campaign_on_meta_node)
graph.add_node("ads_set_meta", ads_set_meta_node)
graph.add_node("ad_creative", ad_creative_node)
graph.add_node("create_ad", create_ad_node)
graph.add_node("summarize_campaign", summarize_campaign_node)
graph.add_node("fetch_metrics", fetch_metrics_node)
graph.add_node("metrics_analyzer", metrics_analyzer_node)
graph.add_node("decide_campaign_action", decide_campaign_action_node)
graph.add_node("modify_campaign_from_decision", modify_campaign_from_decision_node)
#graph.add_node("optimize_campaign_node", optimize_campaign_node)
graph.add_node("send_outreach", email_outreach_node)
graph.add_node("warmup_emails", warmup_email_node)

graph.add_node("google_scraping", google_maps_scraping_node)
graph.add_node("instagram_scraping", instagram_scraping_node)
graph.add_node("send_email", send_email_node)



# Entry Point
graph.set_entry_point("intent_node")

# Intent Branching
graph.add_conditional_edges(
    "intent_node",
    lambda state: state["detected_intent"],
    {
        "launch_campaign": "fetch_product",
        "get_metrics": "fetch_metrics",
        "optimize_campaign": "fetch_metrics",
        "summarize_campaign": "summarize_campaign",
        "refresh_audience": "fetch_product",
        "send_outreach": "send_outreach",
        "warmup_emails": "warmup_emails",
        "google_scrape": "google_scraping",
        "instagram_scrape": "instagram_scraping",
        "send_email":"send_email"

    }
)

# Launch Campaign
graph.add_edge("fetch_product", "analyze_audience")
graph.add_edge("analyze_audience", "create_campaign")
graph.add_edge("create_campaign", "generate_adcopy")
graph.add_edge("generate_adcopy", "create_campaign_on_meta")
graph.add_edge("create_campaign_on_meta", "ads_set_meta")
graph.add_edge("ads_set_meta", "ad_creative")
graph.add_edge("ad_creative", "create_ad")
graph.add_edge("create_ad", END)

# Summarize Campaign
graph.add_edge("summarize_campaign", END)

# Get Metrics add func or tool to provide campaign id used to fetch metrics
#graph.add_edge("get_campaign","fetch_metrics")
#graph.add_edge("fetch_metrics", END)


#Send Email Outreach
graph.add_edge("send_outreach", END)

graph.add_edge("send_email",END)
#Warm emails
graph.add_edge("warmup_emails", END)

#Scrape for leads
graph.add_edge("google_scraping", END)
graph.add_edge("instagram_scraping", END)



# Optimize Campaign
graph.add_edge("fetch_metrics", "metrics_analyzer")
graph.add_edge("metrics_analyzer", "decide_campaign_action")
graph.add_edge("decide_campaign_action", "modify_campaign_from_decision")
graph.add_edge("modify_campaign_from_decision", END)

# === 5. COMPILE ===
campaign_agent_executor = graph.compile()



