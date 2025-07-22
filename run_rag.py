import os
import django
import sys

# ✅ Set up Django environment
sys.path.append(os.path.dirname(__file__))  # Add project root to sys.path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')  # ← your actual settings file
django.setup()
# ✅ Now import and run the function
from agent.tools.rag_setup import setup_product_rag_chroma, fetch_product_from_prompt,embed_campaign
from agent.tools.fetch_product_by_name import fetch_product_by_name,product_usecases_benefits_generator
from agent.tools.analyze_product import analyze_product_audience
from agent.tools.campaign import create_campaign_from_analysis
from agent.tools.launch_campaign import create_campaign_on_meta,ads_set_meta
from agent.tools.utils.date_parser import parse_all_dates
from agent.tools.optimization.campaign_analytics import generate_campaign_summary
from agent.tools.optimization.campaign_analytics import generate_product_adcopy_and_headline_cta
from agent.tools.database_update import update_campaign_fields
# run_rag.py
#from agent.tools.langchain import get_genesis_agent
from agent.tools.langgraph import campaign_agent_executor

from agent.tools.optimization.scheduler import run_optimization
from agent.tools.optimization.metric_fetcher import fetch_campaign_metrics
from agent.tools.optimization.metrics_analyzer import analyze_campaign_metrics
from agent.tools.optimization.decision_maker import decide_campaign_action
import json




#generate_campaign_summary('WEuzJYg')

#run_daily_optimization()

#metrics = fetch_campaign_metrics(campaign_id)
#analysis = analyze_campaign_metrics(metrics)
#decision_data = decide_campaign_action(metrics, analysis)
#print(decision_data)


#if __name__ == "__main__":
 #   agent = get_genesis_agent()
    #setup_product_rag_chroma('Fitness & Wellness Prompt Pack')

  #  while True:
     #   user_input = input("\n🧑 You: ")
      #  if user_input.lower() in {"exit", "quit"}:
       #     print("👋 Goodbye!")
        #    break

        #response = agent.invoke({"input": user_input})
        #print("\n🤖 Agent:", response["output"])

if __name__ == "__main__":
    #from genesis_agent import campaign_agent_executor  # or your import
    while True:
        user_input = input("\n🧑 You: ")
        if user_input.lower() in {"exit", "quit"}:
            print("👋 Goodbye!")
            break

        state = campaign_agent_executor.invoke({"user_input": user_input})
        print("\n🤖 Final Output:")
        if "error" in state:
            print("❌ Error:", state["error"])
        elif "final_ad" in state:
            print("✅ Ad Created:", state["final_ad"])
        else:
            print("📦 State:", json.dumps(state, indent=2, default=str))










