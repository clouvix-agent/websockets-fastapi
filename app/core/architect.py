from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from langchain.schema import SystemMessage, HumanMessage
from langchain.tools import tool
import re

llm = ChatOpenAI(model="gpt-4o-mini")  # You can use any model you prefer

@tool
def architecture_tool(requirement: str, config: RunnableConfig) -> str:
    """
    Helps users design AWS architecture by understanding their application's purpose, use case, and requirements.
    Suggests appropriate AWS services and how they can be used together to achieve the user's goal.

    Args:
        requirement (str): A natural language input from the user describing their application's goals or infrastructure needs.

    Returns:
        str: Markdown-formatted architecture suggestion with appropriate AWS services and interactions.
    """
    print("🏗️ Running architecture_builder_tool")

    user_id = config['configurable'].get('user_id', 'unknown')

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
