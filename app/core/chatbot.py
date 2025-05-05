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
from app.core.tf_generator import generate_terraform_tool, apply_terraform_tool_local, query_inventory, update_terraform_file, read_terraform_files_from_bucket, destroy_terraform_tool_local, get_workspace_status_tool , fetch_metrics
from app.core.architecture_builder import architecture_builder_tool, check_architecture_file
from app.core.tf_generator import TerraformRequest
from langchain.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import InjectedState
from langchain_core.tools import Tool
from langgraph.prebuilt import InjectedState
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables import RunnableConfig
from app.core.github import create_pr
from app.routers.abc import get_recommendations_for_all_metrics

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
tools = [add_two_numbers, search_tool, architecture_builder_tool, generate_terraform_tool, check_architecture_file, get_user_id, apply_terraform_tool_local, query_inventory, update_terraform_file, read_terraform_files_from_bucket, destroy_terraform_tool_local, get_workspace_status_tool, create_pr,fetch_metrics,get_recommendations_for_all_metrics]
llm = ChatOpenAI(model="gpt-4o", temperature=0.1)
llm_with_tools = llm.bind_tools(tools)

import json

def chatbot(state: State):
    messages = state["messages"]

    if not any(isinstance(msg, SystemMessage) for msg in messages):
        tool_names = ", ".join([tool.name for tool in tools])
        system_message = SystemMessage(
            content=(
                "You are an AI assistant that helps users with Terraform-based infrastructure..."
                "After every message, respond ONLY with JSON in this format:"
                '{ "reply": "<main reply>", "suggestions": ["<next step 1>", "<next step 2>", "<next step 3>"] }'
            )
        )
        messages = [system_message] + messages

    # Get LLM response
    response = llm_with_tools.invoke(messages)

    # Ensure response is a JSON string, then wrap it in AIMessage
    # if isinstance(response, str):
    #     return {
    #         "messages": [AIMessage(content=response)],
    #         "suggestions": []
    #     }

    # if isinstance(response, AIMessage):
    #     try:
    #         parsed = json.loads(response.content)
    #         reply = parsed.get("reply", "")
    #         suggestions = parsed.get("suggestions", [])
    #         return {
    #             "messages": [AIMessage(content=json.dumps({
    #                 "reply": reply,
    #                 "suggestions": suggestions
    #             }))],
    #             "suggestions": suggestions
    #         }
    #     except Exception:
    #         return {
    #             "messages": [response],
    #             "suggestions": []
    #         }

    # return {"messages": [response]}
    if isinstance(response, str):
            try:
                parsed = json.loads(response)
                return {
                    "messages": [AIMessage(content=parsed.get("reply", ""))],
                    "suggestions": parsed.get("suggestions", [])
                }
            except json.JSONDecodeError:
                return {
                    "messages": [AIMessage(content=response)],
                    "suggestions": []
                }

    if isinstance(response, AIMessage):
        try:
            parsed = json.loads(response.content)
            return {
                "messages": [AIMessage(content=parsed.get("reply", ""))],
                "suggestions": parsed.get("suggestions", [])
            }
        except json.JSONDecodeError:
            return {
                "messages": [response],
                "suggestions": []
            }

    return {"messages": [response]}


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

async def process_query(query: str, user_id: int = None) -> str:
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
    
    print("State: ", state)
    result = await graph.ainvoke(state, config(user_id))
    
    final_message = result["messages"][-1]
    return final_message.content