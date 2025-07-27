import os
import dotenv
import json
from typing import Annotated

from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from app.core.tf_generator import apply_terraform_tool_local, query_inventory, update_terraform_file, read_terraform_files_from_bucket, destroy_terraform_tool_local, get_workspace_status_tool,fetch_metrics, optimize_resource_by_arn 
from app.core.architecture_builder import architecture_builder_tool, check_architecture_file
from app.core.architect import architecture_tool
from app.core.tf_generator import TerraformRequest
from langchain.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import InjectedState
from langchain_core.tools import Tool
from langgraph.prebuilt import InjectedState
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables import RunnableConfig
from app.core.github import raise_pr_with_tf_code,fetch_tf_files_from_repo
from app.routers.metrics_collector import get_recommendations_for_all_metrics
from app.core.migration_tool import migration_tool

from app.core.tf_agent import generate_terraform_code

memory = MemorySaver()

dotenv.load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

search_tool = TavilySearchResults(max_results=2)

class State(TypedDict):
    messages: Annotated[list, add_messages]
    architecture_json: TerraformRequest
    terraform_git_url: str
    app_git_url: str
    user_id: int


graph_builder = StateGraph(State)

@tool
def add_two_numbers(a: int, b: int) -> int:
    """Add two numbers together"""
    return a + b

@tool
def get_user_id(config: RunnableConfig) -> int:
    """Returns the current user's ID"""
    return f"Your user ID is: {config['configurable'].get('user_id', 'unknown')}"


# def print_user_idd(config: RunnableConfig):
#     """Returns the current user's ID"""
#     return f"Your user ID is: {config['configurable'].get('user_id', 'unknown')}"

tools = []
tools = [add_two_numbers, search_tool, architecture_builder_tool, generate_terraform_code, check_architecture_file, get_user_id, apply_terraform_tool_local, query_inventory, update_terraform_file, read_terraform_files_from_bucket, destroy_terraform_tool_local, get_workspace_status_tool,get_recommendations_for_all_metrics,fetch_metrics, architecture_tool, optimize_resource_by_arn,fetch_tf_files_from_repo,raise_pr_with_tf_code,migration_tool]
llm = ChatOpenAI(model="gpt-4o", temperature=0.1)
llm_with_tools = llm.bind_tools(tools)

import json

def chatbot(state: State):
    messages = state["messages"]

    if not any(isinstance(msg, SystemMessage) for msg in messages):
        system_message = SystemMessage(
            content=(
                "You are an AI assistant that helps users with Terraform-based infrastructure.\n"
                "Always reply in the following JSON format:\n"
                '{ "reply": "<your main answer>", "suggestions": ["<next step 1>", "<next step 2>", "<next step 3>"] }\n\n'
                "If you're unable to generate suggestions, include general ones about Terraform.\n\n"
                "IMPORTANT: When users ask to generate Terraform code, encourage them to include a project name in their request.\n"
                "You should extract project names from the user's query automatically, but if none is found, you should ask the user to provide one.\n"
                
            )
        )
        messages = [system_message] + messages

    response = llm_with_tools.invoke(messages)

    fallback_suggestions = [
        "Generate Terraform code",
        "Apply infrastructure configuration",
        "Optimize cloud costs"
    ]

    if isinstance(response, AIMessage):
        try:
            parsed = json.loads(response.content)

            # ✅ Fallback if suggestions missing or empty
            suggestions = parsed.get("suggestions")
            if not suggestions or not isinstance(suggestions, list) or len(suggestions) == 0:
                suggestions = fallback_suggestions

            return {
                "messages": [AIMessage(content=parsed.get("reply", ""))],
                "reply": parsed.get("reply", ""),
                "suggestions": suggestions
            }

        except Exception as e:
            print("❌ JSON parsing error in chatbot():", e)
            return {
                "messages": [response],
                "reply": response.content,
                "suggestions": fallback_suggestions
            }

    return {
        "messages": [response],
        "reply": response.content,
        "suggestions": fallback_suggestions
    }





graph_builder.add_node("chatbot", chatbot)

tool_node = ToolNode(tools)
print("Adding tool node to the graph")
graph_builder.add_node("tools", tool_node)

graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
)

graph_builder.add_edge("tools", "chatbot")
graph_builder.set_entry_point("chatbot")
graph = graph_builder.compile(checkpointer=memory)

config = lambda user_id: {
    "configurable": {
        "thread_id": "1",
        "user_id": user_id  # ✅ inject user_id into config
    }
}

async def process_query(query: str, user_id: int = None) -> dict:
    messages = [
        {
            "role": "user",
            "content": query,
        }
    ]
    print("Processing query: ", query)
    
    state = {
        "messages": messages,
        "architecture_json": "",
        "terraform_git_url": "",
        "app_git_url": "",
        "user_id": user_id
    }

    result = await graph.ainvoke(state, config(user_id))
    
    final_message = result["messages"][-1]
    
    print("Final Message")
    print(final_message)
    print("Final Message Content")
    print(final_message.content)

    return {
        "reply": result.get("reply", final_message.content),
        "suggestions": result.get("suggestions", [])  # ✅ Extract suggestions properly
    }