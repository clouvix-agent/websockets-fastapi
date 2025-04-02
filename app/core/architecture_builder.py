import os
from langchain_core.tools import tool

@tool
def architecture_builder_tool():
    """Opens the architecture UI and waits for the JSON output. Runs when the user asks to build the architecture diagram."""
    print("Architecture creation tool initialed visit http://localhost:8080")
    return "Architecture creation tool initialed visit http://localhost:8080"

@tool
def check_architecture_file():
    """Checks if the architecture file exists and returns the content."""
    print("Checking if the architecture file exists")
    if os.path.exists("architecture_json/request.json"):
        print("Inside architecture file")
        with open("architecture_json/request.json", "r") as f:
            return f.read()
    return "No architecture file found"
