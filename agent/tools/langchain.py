from langchain_openai import ChatOpenAI

from langchain.agents import (
    create_openai_functions_agent,
    create_tool_calling_agent,
    initialize_agent,
    AgentType
)

from langchain.agents import AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

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
from langchain.chat_models import init_chat_model

from langchain_core.memory import ConversationBufferMemory
if not os.environ.get("OPENAI_API_KEY"):
  os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter API key for OpenAI: ")

#🛠List of all tools
tool_list = [
fetch_product_by_name,
fetch_campaign_by_name,
analyze_product_audience,
product_usecases_benefits_generator,
create_campaign_from_analysis,
create_campaign_on_meta,
ad_creative,
create_ad,
ads_set_meta,
setup_product_rag_chroma,
fetch_interests,
parse_all_dates,


#database update
refresh_all_vector_dbs,


#optimization
fetch_campaign_metrics,
analyze_campaign_metrics,
analyze_all_active_campaign_metrics,
decide_campaign_action,
modify_campaign_from_decision,
pause_campaign,
scale_campaign,
clone_campaign,
refresh_creative,
update_audience_targeting,
revise_offer_logic,
optimize_campaign_budget,
fetch_all_active_campaign_metrics,
decide_all_active_campaign_metrics_actions,
generate_campaign_summary,
generate_product_adcopy_and_headline_cta,

#scheduler
run_optimization,


    ]


# LLM

llm = ChatOpenAI("gpt-4", model_provider="openai")
# Wrap tools

# Prompt
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are GenesisAI, a profit-first digital ad strategist."),
    ("user", "{input}"),
    ("assistant", "{agent_scratchpad}")
])


agent = create_tool_calling_agent(llm, tool_list, prompt)
# Return executor
def get_genesis_agent():
    agent_executor = AgentExecutor(agent=agent, tools=tool_list)

    return agent_executor