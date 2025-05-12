import os
import re
import json
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from langchain.schema import SystemMessage, HumanMessage
from langchain_core.tools import tool

llm = ChatOpenAI(model="gpt-4o-mini")

@tool
def architecture_tool(action: str = "explain", requirement: str = "", config: RunnableConfig = {}) -> str:
    """
    A unified architecture tool that either:
    1. Opens the architecture diagram UI,
    2. Checks and summarizes an existing architecture JSON file,
    3. Or explains what AWS services to use based on a described use case.

    Args:
        action (str): One of ['draw', 'check', 'explain']
        requirement (str): User-described app or infra need (used only for 'explain')
        config (RunnableConfig): Includes user_id

    Returns:
        str: A message, markdown summary, or architecture recommendation.
    """
    print(f"🛠️ Running architecture_tool with action: {action}")
    user_id = config.get('configurable', {}).get('user_id', 'unknown')

    if action == "draw":
        return "📐 Open the architecture diagram builder here: https://architecture.clouvix.com"

    elif action == "check":
        print("🔎 Checking if architecture file exists...")
        path = "architecture_json/request.json"
        if os.path.exists(path):
            with open(path, "r") as f:
                try:
                    data = json.load(f)
                    return f"✅ Found architecture file:\n```json\n{json.dumps(data, indent=2)}\n```"
                except json.JSONDecodeError:
                    return "⚠️ Architecture file is not valid JSON."
        return "❌ No architecture file found."

    elif action == "explain":
        if not requirement.strip():
            return "❌ Please provide a valid `requirement` to explain the AWS architecture."
        
        messages = [
            SystemMessage(content="""
                You are an expert AWS solutions architect.
                Based on the user's requirements, analyze the application use case and suggest the most suitable AWS services.
                Clearly explain:
                - The purpose of each recommended AWS service
                - How these services interact with each other
                - Any IAM roles, networking, or monitoring considerations
                Format your response in Markdown, using bullet points and subheadings for clarity.
                Keep the output concise and actionable for infrastructure planning.
            """),
            HumanMessage(content=f"""
                The user has described their application or goal as follows:

                {requirement.strip()}

                Suggest the optimal AWS architecture and services for this use case.
            """)
        ]

        try:
            response = llm.invoke(messages)
            markdown_output = re.sub(r"```markdown|```", "", response.content.strip()).strip()
            return markdown_output
        except Exception as e:
            return f"❌ Architecture suggestion failed: {str(e)}"

    else:
        return f"❌ Unknown action '{action}'. Valid options are: 'draw', 'check', or 'explain'."
