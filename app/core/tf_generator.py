import json
import yaml
import os
import re
import subprocess
import requests
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from langgraph.prebuilt import InjectedState
from langchain.tools import tool
from app.database import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceCreate
from app.db.workspace import create_workspace
from app.auth.deps import get_current_active_user
from app.auth.utils import SECRET_KEY, ALGORITHM
from jose import JWTError, jwt
from langchain_core.runnables import RunnableConfig
# from app.models.connection import Connection
from app.db.connection import get_user_connections_by_type
from minio import Minio
import shutil
import tempfile 
from minio.error import S3Error


# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TERRAFORM_API_TOKEN = os.getenv("TERRAFORM_API_TOKEN")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")

# Ensure terraform directory exists
TERRAFORM_DIR = "terraform"

app = FastAPI()

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins. Change this to ["http://localhost:3000"] for security.
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Create OpenAI Chat Model
llm = ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-4o-mini")

# Load Knowledge Base
with open("service_dependency_kb.yaml", "r") as kb_file:
    SERVICE_DEPENDENCY_KB = yaml.safe_load(kb_file)

with open("terraform_resource_kb.json", "r") as kb_file:
    TERRAFORM_RESOURCE_KB = json.load(kb_file)


# Define Pydantic models for request validation
class Service(BaseModel):
    id: str
    type: str
    label: str
    githubRepo: str


class Connection(BaseModel):
    from_: str  # Use from_ since 'from' is a reserved keyword
    to: str


class TerraformRequest(BaseModel):
    project_name: str
    services: list[Service]
    connections: list[Connection]

# **Hardcoded User Input JSON**
# USER_INPUT_JSON = {
#   "services": [
#     {
#       "id": "1",
#       "type": "ecs",
#       "label": "ECS Cluster",
#       "githubRepo": ""
#     },
#     {
#       "id": "2",
#       "type": "s3",
#       "label": "S3 Bucket",
#       "githubRepo": ""
#     },
#     {
#       "id": "3",
#       "type": "ecr",
#       "label": "ECR Repository",
#       "githubRepo": ""
#     },
#     {
#       "id": "4",
#       "type": "lambda",
#       "label": "Lambda Function",
#       "githubRepo": ""
#     }
#   ],
#   "connections": [
#     {
#       "from": "ecs",
#       "to": "s3"
#     },
#     {
#       "from": "ecr",
#       "to": "ecs"
#     },
#     {
#       "from": "lambda",
#       "to": "s3"
#     }
#   ]
# }

def query_knowledge_base(user_services):
    """
    Query the Knowledge Base to get service details and dependencies.
    """
    service_details = {}

    for service in user_services:
        service_type = service.type

        # Get dependencies from Service Dependency KB
        dependencies = SERVICE_DEPENDENCY_KB.get(service_type, {})

        # Get Terraform details from Terraform Resource KB
        terraform_info = TERRAFORM_RESOURCE_KB.get(f"aws_{service_type}", {})

        service_details[service_type] = {
            "user_input": service.dict(),
            "dependencies": dependencies,
            "terraform_info": terraform_info,
        }

    return service_details

def build_openai_prompt(project_name, service_details, user_connections):
    """
    Constructs a structured OpenAI message prompt for generating Terraform code.
    """
    print("===== BUILD OPENAI MESSAGE =====\n")
    print(f"Project Name: {project_name}")
    print("\n===== SERVICE DETAILS =====\n")
    print(json.dumps(service_details, indent=2))  # Pretty print JSON
    print("\n===== USER CONNECTIONS =====\n")
    print(json.dumps([conn.dict() for conn in user_connections], indent=2))  # Convert Pydantic models to dicts for logging

    system_message = SystemMessage(
        content="You are a Terraform file generator. Your task is to generate precise Terraform infrastructure "
                "configuration in accordance with user requirements. Consider connections between services, "
                "IAM roles, security groups, and dependencies."
                "You just have to prepare infrasturcutre for the user, don't include any code or deployment related configuration."
    )

    user_prompt = f"Generate Terraform code for the following infrastructure project: **{project_name}**\n\n"

    for service_type, details in service_details.items():
        resource_name = f"{project_name.lower()}_{service_type}"

        # Convert Pydantic model to dictionary for JSON serialization
        user_input_dict = details["user_input"].dict() if hasattr(details["user_input"], "dict") else details["user_input"]

        user_prompt += f"### {user_input_dict['label']} ({service_type})\n"
        user_prompt += f"- **User Requirement:** {json.dumps(user_input_dict, indent=2)}\n"
        user_prompt += f"- **Use my project name: `{resource_name}`** to generate unique and meaningful names for Terraform resources.\n"
        user_prompt += f"- **Ensure connections are handled properly, including IAM roles, policies, security groups, and networking.**\n"
        user_prompt += f"- **Do NOT include function code, Docker image URLs, or any deployment-related configuration.**\n"

        if details["dependencies"]:
            user_prompt += f"- **Required Dependencies:** {json.dumps(details['dependencies'].get('mandatory_resources', {}), indent=2)}\n"
            user_prompt += f"- **Optional Dependencies:** {json.dumps(details['dependencies'].get('optional_resources', {}), indent=2)}\n"

        if details["terraform_info"]:
            user_prompt += f"- **Terraform Required Parameters:** {json.dumps(details['terraform_info'].get('required', {}), indent=2)}\n"
            user_prompt += f"- **Terraform Optional Parameters:** {json.dumps(details['terraform_info'].get('optional', {}), indent=2)}\n"
            user_prompt += f"- **Terraform Best Practices:** {json.dumps(details['terraform_info'].get('best_practices', {}), indent=2)}\n"
            
        user_prompt += "\n"

    # Add Connection Details
    user_prompt += "### Connections:\n"
    for connection in user_connections:
        user_prompt += f"- {connection.from_} connects to {connection.to}\n"  # ✅ Use `.from_` instead of dictionary access

    user_prompt += """
    Generate the Terraform code following AWS best practices:
    - Ensure all required dependencies are properly referenced.
    - Use correct IAM roles and networking configurations.
    - Follow infrastructure-as-code best practices.
    - Ensure syntax correctness and proper indentation.
    - The output should only contain valid Terraform HCL code, without explanations. Region should be us-east-1.
    """

    return [system_message, HumanMessage(content=user_prompt)]


def generate_terraform(messages):
    """
    Calls OpenAI via LangChain with structured messages.
    """
    try:
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI: {e}")
        return ""


def validate_terraform_with_openai(terraform_code, services, connections):
    """Send Terraform file + user input (services & connections) to OpenAI for logical validation."""
    
    # Convert Pydantic models to dictionaries for JSON serialization
    services_dict = [service.dict() if hasattr(service, "dict") else service for service in services]
    connections_dict = [connection.dict() if hasattr(connection, "dict") else connection for connection in connections]

    messages = [
        SystemMessage(content="You are an expert Terraform engineer. Validate the Terraform file to ensure it meets the user's requirements."),
        HumanMessage(content=f"""
        The user wants to deploy the following AWS infrastructure:

        **Services:**
        ```json
        {json.dumps(services_dict, indent=2)}
        ```

        **Connections:**
        ```json
        {json.dumps(connections_dict, indent=2)}
        ```
        Check if each connection is being handled properly, including IAM roles, policies, security groups, and networking for connecting required services.

        **Terraform Configuration:**
        ```hcl
        {terraform_code}
        ```

        **Validation Request:**
        - Does this Terraform file achieve the user's intended goal?
        - If yes, return the entire Terraform file as is.
        - If no, update it to align with the user's infrastructure requirements and return the complete corrected Terraform configuration.
        - Ensure: Do NOT include function code, Docker image URLs, or any deployment-related configuration.
        - The response should only contain valid Terraform HCL code, without explanations.
        - Make sure: Do NOT include function code, Docker image URLs, or any deployment-related configuration.
        """)
    ]

    response = llm.invoke(messages)
    terraform_code = re.sub(r"```hcl|```", "", response.content.strip()).strip()
    
    # **Step 2: Ensure all connections are included**
    print("🔎 Running OpenAI validation for missing connections...")
    messages = [
        SystemMessage(content="You are an expert Terraform engineer. Validate that the Terraform file includes all required service connections."),
        HumanMessage(content=f"""
        The user wants the following service connections:

        **Connections:**
        ```json
        {json.dumps(connections_dict, indent=2)}
        ```

        **Current Terraform Configuration:**
        ```hcl
        {terraform_code}
        ```

        **Validation Request:**
        - Ensure all the required connections between services are properly handled in the Terraform file.
        - If any connection is missing, **ONLY add the missing connection** (e.g., security groups, IAM roles, networking rules, etc.).
        - **DO NOT remove or modify any existing connections**.
        - If all required connections are already present, return the Terraform file as it is.
        - The response should contain only the entire valid Terraform HCL file without explanations.
        """)
    ]

    response = llm.invoke(messages)
    terraform_code = re.sub(r"```hcl|```", "", response.content.strip()).strip()

    return terraform_code


# def run_terraform_plan():
#     """Runs 'terraform init' and 'terraform plan' to validate the Terraform configuration."""
#     try:
#         # Ensure TERRAFORM_DIR exists
#         if not os.path.exists(TERRAFORM_DIR):
#             os.makedirs(TERRAFORM_DIR, exist_ok=True)
#             print(f"Created Terraform directory: {TERRAFORM_DIR}")
            
#         subprocess.run(["terraform", "init"], cwd=TERRAFORM_DIR, check=True)
#         result = subprocess.run(["terraform", "plan"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
        
#         if result.returncode == 0:
#             print("✅ Terraform Plan: Successful")
#             return True, ""
#         else:
#             print("❌ Terraform Plan Error:\n", result.stderr)
#             return False, result.stderr
#     except subprocess.CalledProcessError as e:
#         print(f"Terraform execution failed: {e}")
#         return False, str(e)

def fix_terraform_with_openai(terraform_code, terraform_error):
    """Send the incorrect Terraform code and error message to OpenAI to get a fixed version."""
    messages = [
        SystemMessage(content="You are an expert Terraform engineer. Your task is to fix any Terraform errors."),
        HumanMessage(content=f"""
        The following Terraform configuration has an error:

        ```hcl
        {terraform_code}
        ```

        The Terraform error message is:

        ```
        {terraform_error}
        ```

        Please correct the Terraform code and return the **entire** fixed configuration.
        Ensure that:
        - Do NOT include function code, Docker image URLs, s3_key, or any deployment-related configuration.
        - The Terraform file is completely corrected.
        - The configuration follows best practices.
        - The output should only contain valid Terraform HCL code, without explanations.
        """)
    ]

    response = llm.invoke(messages)
    terraform_output = re.sub(r"```hcl|```", "", response.content.strip()).strip()
    print(f"Terraform output: {terraform_output}")
    return terraform_output

# def run_terraform_apply_and_destroy():
#     """Runs 'terraform apply' to provision the Terraform infrastructure and then runs 'terraform destroy'."""
#     try:
#         # Ensure TERRAFORM_DIR exists
#         if not os.path.exists(TERRAFORM_DIR):
#             os.makedirs(TERRAFORM_DIR, exist_ok=True)
#             print(f"Created Terraform directory: {TERRAFORM_DIR}")
            
#         # Run Terraform Apply
#         result_apply = subprocess.run(["terraform", "apply", "-auto-approve"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
#         print("===== TERRAFORM APPLY RESULT =====\n")
#         print(result_apply.stdout)

#         if result_apply.returncode == 0:
#             print("✅ Terraform Apply: Successful")

#             # Save apply output to a file
#             with open(os.path.join(TERRAFORM_DIR, "terraform_apply_output.txt"), "w") as f:
#                 f.write(result_apply.stdout)

#             # Run Terraform Destroy
#             print("\n⚠️ Running Terraform Destroy to clean up resources...\n")
#             result_destroy = subprocess.run(["terraform", "destroy", "-auto-approve"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
#             print("===== TERRAFORM DESTROY RESULT =====\n")
#             print(result_destroy.stdout)

#             if result_destroy.returncode == 0:
#                 print("✅ Terraform Destroy: Successful")
#                 return True, "Apply and Destroy completed successfully."
#             else:
#                 print("❌ Terraform Destroy Error:\n", result_destroy.stderr)
#                 return False, result_destroy.stderr
#         else:
#             print("❌ Terraform Apply Error:\n", result_apply.stderr)
#             print("\n⚠️ Running Terraform Destroy to clean up resources...\n")
#             result_destroy = subprocess.run(["terraform", "destroy", "-auto-approve"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
#             print("===== TERRAFORM DESTROY RESULT =====\n")
#             print(result_destroy.stdout)
#             return False, result_apply.stderr
#     except subprocess.CalledProcessError as e:
#         print(f"Terraform execution failed: {e}")
#         return False, str(e)

def validate_terraform_api(terraform_file_path):
    """Validates Terraform configuration using the external API endpoint"""
    try:
        # Prepare the variables JSON
        variables = {
            "aws_access_key": AWS_ACCESS_KEY,
            "aws_secret_key": AWS_SECRET_KEY
        }

        # Prepare the API request
        url = "https://terraform.clouvix.com/validate"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {TERRAFORM_API_TOKEN}"
        }

        # Open and prepare the terraform file
        with open(terraform_file_path, 'rb') as tf_file:
            files = {
                'terraform_file': ('main.tf', tf_file, 'text/plain'),
                'variables': (None, json.dumps(variables))
            }

            # Make the API request
            response = requests.post(url, headers=headers, files=files)
            response_data = response.json()

            # Check if the response indicates success
            if response_data.get("success") is True:
                return True, ""
            else:
                # Extract error message from the response
                error_message = response_data.get("error", "")
                print(f"Error message: {error_message}")
                if not error_message and "details" in response_data:
                    error_message = response_data["details"].get("message", "Unknown error occurred")
                return False, error_message

    except Exception as e:
        return False, str(e)

def validate_and_fix_terraform(terraform_code, services, connections):
    """Runs OpenAI validation, then API validation, fixing errors in a loop until successful."""
    
    print("🔎 Running OpenAI validation for completeness...")
    terraform_code = validate_terraform_with_openai(terraform_code, services, connections)
    return terraform_code
    # attempt = 0
    # while True:
    #     attempt += 1
    #     print(f"\n🔄 Terraform Validation Attempt {attempt}")

    #     # Ensure terraform directory exists
    #     if not os.path.exists(TERRAFORM_DIR):
    #         os.makedirs(TERRAFORM_DIR, exist_ok=True)
    #         print(f"Created Terraform directory: {TERRAFORM_DIR}")

    #     # Save the Terraform configuration
    #     terraform_file_path = os.path.join(TERRAFORM_DIR, "main.tf")
    #     with open(terraform_file_path, "w") as tf_file:
    #         tf_file.write(terraform_code)

    #     # Validate using API
    #     success, error_message = validate_terraform_api(terraform_file_path)
    #     if success:
    #         print("🎉 Terraform Validation Successful!")
    #         return terraform_code
    #     else:
    #     # Fix errors if validation failed
    #         print(f"🛠️ Fixing Terraform validation errors... (Attempt {attempt})")
    #         terraform_code = fix_terraform_with_openai(terraform_code, error_message)
            
    #         # Save the updated Terraform configuration
    #         with open(terraform_file_path, "w") as tf_file:
    #             tf_file.write(terraform_code)
    #         continue

    # print("🔴 Terraform Validation Failed after 5 attempts")
    # return terraform_code

def extract_and_save_terraform(terraform_output, services, connections, user_id, project_name, request):
    """Extracts Terraform configurations, validates, fixes errors, and saves the final file."""
    if not terraform_output:
        print("Error: No Terraform code generated.")
        return

    terraform_output = re.sub(r"```hcl|```", "", terraform_output).strip()

    # Create terraform directory if it doesn't exist
    if not os.path.exists(TERRAFORM_DIR):
        os.makedirs(TERRAFORM_DIR, exist_ok=True)
        print(f"Created Terraform directory: {TERRAFORM_DIR}")

    # Validate and Fix Terraform Configuration
    validated_code = validate_and_fix_terraform(terraform_output, services, connections)

    # Save the final validated Terraform file
    final_tf_path = os.path.join(TERRAFORM_DIR, "main.tf")
    with open(final_tf_path, "w") as tf_file:
        tf_file.write(validated_code)

    print(request)
    # Add an entry to workspace table
    db: Session = next(get_db())
    new_workspace = WorkspaceCreate(
        userid=user_id,
        wsname=project_name,
        filetype="terraform",
        filelocation=final_tf_path,
        diagramjson={},
        githublocation=""
    )
    create_workspace(db=db, workspace=new_workspace)
    print(f"\n✅ Final validated Terraform file saved at: {final_tf_path}")

# def generate_terraform_tool(state: InjectedState):
#     """
#     Tool function to orchestrate Terraform generation and file extraction. Takes in a TerraformRequest object that contains the project name, services, and connections.
#     """
#     return {
#         "name": "generate_terraform",
#         "description": "Generates Terraform infrastructure code based on the architecture specification",
#         "function": lambda: generate_terraform_endpoint(state["architecture_json"]),
#         "coroutine": True
#     }

def get_terraform_folder(project_name: str) -> str:
    """Create a numbered terraform folder based on project name"""
    base_folder = f"{project_name}_terraform"
    folder = base_folder
    counter = 1
    
    while os.path.exists(folder):
        folder = f"{project_name}_{counter}_terraform"
        counter += 1
        
    os.makedirs(folder, exist_ok=True)
    return folder

@tool
def generate_terraform_tool(config: RunnableConfig) -> str:
    """Main function to orchestrate Terraform generation and file extraction.
    Reads the architecture JSON file and runs the terraform code generation and returns the terraform file content."""
    
    print("Running generate_terraform_tool")
    
    user_id = config['configurable'].get('user_id', 'unknown')
    # **Step 1: Check and create necessary directories**
    if not os.path.exists("architecture_json"):
        os.makedirs("architecture_json", exist_ok=True)
        print("Created architecture_json directory")
    
    # **Step 2: Extract User Requirements**
    request = None
    architecture_file = "architecture_json/request.json"
    
    if not os.path.exists(architecture_file):
        error_msg = f"Error: Architecture file not found at {architecture_file}"
        print(error_msg)
        raise FileNotFoundError(error_msg)
    
    try:
        with open(architecture_file, "r") as f:
            request_data = json.loads(f.read())
            print(f"Successfully read architecture file: {request_data}")
            request = TerraformRequest(**request_data)
    except json.JSONDecodeError as e:
        error_msg = f"Error: Invalid JSON format in architecture file: {str(e)}"
        print(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Error reading or parsing architecture file: {str(e)}"
        print(error_msg)
        raise Exception(error_msg)
    
    print(f"Received request: {request}")
    
    # Create numbered terraform folder
    terraform_dir = get_terraform_folder(request.project_name)
    
    # Update global TERRAFORM_DIR for other functions
    global TERRAFORM_DIR
    TERRAFORM_DIR = terraform_dir
    
    os.makedirs(TERRAFORM_DIR, exist_ok=True)
    print(f"Created Terraform directory: {TERRAFORM_DIR}")
    
    project_name = request.project_name
    user_services = request.services
    user_connections = request.connections
    
    # **Step 3: Query Knowledge Base**
    try:
        service_details = query_knowledge_base(user_services)
        print("Successfully queried knowledge base")
    except Exception as e:
        error_msg = f"Error querying knowledge base: {str(e)}"
        print(error_msg)
        raise Exception(error_msg)

    # **Step 4: Build OpenAI Messages**
    try:
        openai_messages = build_openai_prompt(project_name, service_details, user_connections)
        print("Successfully built OpenAI messages")
    except Exception as e:
        error_msg = f"Error building OpenAI messages: {str(e)}"
        print(error_msg)
        raise Exception(error_msg)

    # **Step 5: Call OpenAI API**
    try:
        terraform_output = generate_terraform(openai_messages)
        if not terraform_output:
            error_msg = "Error: No Terraform code was generated"
            print(error_msg)
            raise ValueError(error_msg)
        print("Successfully generated Terraform code")
    except Exception as e:
        error_msg = f"Error generating Terraform code: {str(e)}"
        print(error_msg)
        raise Exception(error_msg)

    # **Step 6: Extract and Save Terraform File**
    try:
        extract_and_save_terraform(terraform_output, user_services, user_connections, user_id, project_name, request_data)
        print(f"Successfully saved Terraform file to {TERRAFORM_DIR}/main.tf")
    except Exception as e:
        error_msg = f"Error saving Terraform file: {str(e)}"
        print(error_msg)
        raise Exception(error_msg)
    
    # Read the generated Terraform file and return its contents with a success message
    try:
        with open(os.path.join(TERRAFORM_DIR, "main.tf"), "r") as f:
            terraform_content = f.read()
#             return f"""
# ```hcl
# {terraform_content}
# ```

# You can now proceed with applying this Terraform configuration."""
    except Exception as e:
        error_msg = f"Error reading generated Terraform file: {str(e)}"
        print(error_msg)
        raise Exception(error_msg)
    

    print("📤 Uploading Terraform directory to MinIO...")

    minio_client = Minio(
        "storage.clouvix.com",
        access_key="clouvix@gmail.com",
        secret_key="Clouvix@bangalore2025",
        secure=True
    )

    print(minio_client)

    bucket_name = f"terraform-workspaces-user-{user_id}"

    print(minio_client.bucket_exists(bucket_name))
        # Create bucket if it doesn't exist
    if not minio_client.bucket_exists(bucket_name):
        print("Inside Make bucket")
        minio_client.make_bucket(bucket_name)
        print(f"🪣 Created bucket: {bucket_name}")
    else:
        print(f"📦 Bucket exists: {bucket_name}")

    folder_name = os.path.basename(TERRAFORM_DIR.rstrip("/"))  # Same as directory name

        # Upload each file with folder_name prefix
    for root, _, files in os.walk(TERRAFORM_DIR):
        for file in files:
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, TERRAFORM_DIR)
            object_key = f"{folder_name}/{relative_path}"
            print(f"⬆️ Uploading: {file_path} -> {object_key}")
            minio_client.fput_object(bucket_name, object_key, file_path)

    print("✅ Terraform directory uploaded to MinIO!")

    try:
        shutil.rmtree(TERRAFORM_DIR)
        print(f"🧹 Deleted local Terraform directory: {TERRAFORM_DIR}")
    except Exception as e:
        print(f"⚠️ Failed to delete local Terraform directory: {e}")


    return f"""
        ```hcl
        {terraform_content}
        ```
        You can now proceed with adding user inputs required this Terraform configuration and then proceed with applying."""

    
    
        
# @tool    
# def terraform_apply_tool(terraform_file_path, config: RunnableConfig):
#     """Helps run terraform apply on terraform file"""
#     print("Using apply tool")
#     user_id = config['configurable'].get('user_id', 'unknown')
#     print("User id")
#     print(user_id)
#     try:
#         # Get the database session
#         db: Session = next(get_db())
#         print("Inside try")

#         # Query the connections table to get the connection_json for the given user_id
#         connections = db.query(Connection).filter(
#             Connection.userid == user_id,
#             Connection.type == "aws"
#         ).all()
        
#         print("Found connections:", connections)
#         if not connections:
#             print("Errored here")
#             raise ValueError(f"No AWS connection found for user_id: {user_id}")

#         # Get the first connection (assuming there's only one AWS connection per user)
#         connection = connections[0]
#         print("Using connection:", connection)

#         # Parse the connection_json to extract AWS_ACCESS_KEY and AWS_SECRET_KEY
#         print("Iam here")
#         connection_data = json.loads(connection.connection_json)
#         print("Connection data:", connection_data)
#         aws_access_key = next((item["value"] for item in connection_data if item["key"] == "AWS_ACCESS_KEY_ID"), None)
#         aws_secret_key = next((item["value"] for item in connection_data if item["key"] == "AWS_SECRET_ACCESS_KEY"), None)

#         if not aws_access_key or not aws_secret_key:
#             raise ValueError("AWS credentials not found in the connection data")
        
#         print("AWS Secret Key:", aws_secret_key)
#         print("AWS Access Key:", aws_access_key)
#         # Prepare the variables JSON
#         variables = {
#             "aws_access_key": aws_access_key,
#             "aws_secret_key": aws_secret_key
#         }

#         # Prepare the API request
#         url = "http://localhost:8001/execute"
#         headers = {
#             "accept": "application/json",
#             "Authorization": f"Bearer {TERRAFORM_API_TOKEN}"
#         }

#         # Open and prepare the terraform file
#         with open(terraform_file_path, 'rb') as tf_file:
#             files = {
#                 'terraform_file': ('main.tf', tf_file, 'text/plain'),
#                 'variables': (None, json.dumps(variables))
#             }

#             # Make the API request
#             response = requests.post(url, headers=headers, files=files)
#             response_data = response.json()

#             # Check if the response indicates success
#             # if response_data.get("success") is True:
#             #     return True, ""
#             # else:
#             #     # Extract error message from the response
#             #     error_message = response_data.get("error", "")
#             #     print(f"Error message: {error_message}")
#             #     if not error_message and "details" in response_data:
#             #         error_message = response_data["details"].get("message", "Unknown error occurred")
#             #     return False, error_message
#             print(response_data)
#         return response_data

#     except Exception as e:
#         return False, str(e)

# def main():
#     """
#     Main function to orchestrate Terraform generation and file extraction.
#     """
#     print("\n===== STARTING TERRAFORM GENERATION =====\n")

#     # **Step 1: Extract User Requirements**
#     user_services = USER_INPUT_JSON["services"]
#     user_connections = USER_INPUT_JSON["connections"]

#     # **Step 2: Query Knowledge Base**
#     service_details = query_knowledge_base(user_services)

#     # **Step 3: Build OpenAI Messages**
#     openai_messages = build_openai_prompt(service_details, user_connections)

#     print("===== OPENAI MESSAGE =====\n")
#     for message in openai_messages:
#         print(message.content)

#     # **Step 4: Call OpenAI API**
#     terraform_output = generate_terraform(openai_messages)
#     print("===== TERRAFORM OUTPUT =====\n")
#     print(terraform_output)

#     # **Step 5: Extract and Save Terraform File**
#     extract_and_save_terraform(terraform_output, user_services, user_connections)
    # Rest of the existing implementation...
    # Return content of terraform file


def load_inventory():
    with open("aws_comprehensive_inventory.json", "r") as f:
        return json.load(f)

# Query the inventory using LangChain
@tool
def query_inventory(user_query: str) -> str:
    """
    Query the AWS inventory based on the user's query and return the result.
    
    Args:
        user_query (str): The query to be answered based on the AWS inventory.
    
    Returns:
        str: The response from the AWS inventory assistant.
    """
    print("Using Inventory Tool")
    # Load inventory
    inventory = load_inventory()

    # Define the system message
    system_message = SystemMessage(
        content=(
            "You are an AWS inventory assistant. The following is the current AWS inventory:"
            f"\n{json.dumps(inventory, indent=2)}"
            f"\nBased on this inventory, answer the following question: {user_query}"
        )
    )

    # Create a human message with the user's query
    human_message = HumanMessage(content=user_query)

    # Run the query using the LLM
    response = llm.invoke([system_message, human_message])

    # Print the response
    print("Query Result:", response.content)
    return response.content


@tool
def update_terraform_file(user_update_prompt: str, project_name: str, config: RunnableConfig) -> str:
    """
    Tool to update the existing Terraform configuration based on user instructions.

    Args:
        user_update_prompt (str): Description of the changes user wants to make in the Terraform config.

    Returns:
        str: Updated Terraform code or error message.
    """
    print("🔧 Running update_terraform_file tool")


    user_id = config['configurable'].get('user_id', 'unknown')
    bucket_name = f"terraform-workspaces-user-{user_id}"
    folder_name = f"{project_name}_terraform"

    # Create a temporary local directory
    temp_dir = tempfile.mkdtemp()
    download_path = os.path.join(temp_dir, folder_name)
    os.makedirs(download_path, exist_ok=True)

    try:
        # Initialize MinIO client
        minio_client = Minio(
            "storage.clouvix.com",
            access_key="clouvix@gmail.com",
            secret_key="Clouvix@bangalore2025",
            secure=True
        )

        print(f"📥 Downloading `{folder_name}/` from `{bucket_name}`...")

        # Download files from MinIO
        objects = minio_client.list_objects(bucket_name, prefix=f"{folder_name}/", recursive=True)
        for obj in objects:
            object_key = obj.object_name
            relative_path = object_key[len(folder_name) + 1:]  # Remove prefix from object key
            local_path = os.path.join(download_path, relative_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            minio_client.fget_object(bucket_name, object_key, local_path)
            print(f"⬇️  {object_key} -> {local_path}")

        # Locate main.tf
        terraform_file_path = os.path.join(download_path, "main.tf")
        if not os.path.exists(terraform_file_path):
            raise FileNotFoundError("❌ main.tf not found in the downloaded folder.")

        # Read current Terraform config
        with open(terraform_file_path, "r") as file:
            existing_code = file.read()

        # Compose messages for LLM
        messages = [
            SystemMessage(content="You are an expert Terraform engineer. Your job is to update an existing Terraform configuration based on user requirements."),
            HumanMessage(content=f"""Here is the current Terraform configuration:
                ```hcl
                {existing_code}
                ```
                The user wants the following changes:

                Copy
                Edit
                {user_update_prompt}
                Please update the configuration accordingly and return the entire updated Terraform code, using best practices.

                Important:

                Only include valid Terraform HCL, no explanation.

                Do NOT remove unrelated infrastructure unless specified.

                Do NOT include deployment or function code.""") ]

  # Call LLM to get updated code
        response = llm.invoke(messages)
        updated_code = re.sub(r"```hcl|```", "", response.content.strip()).strip()

        # Write updated code to main.tf
        with open(terraform_file_path, "w") as file:
            file.write(updated_code)

        print("✅ main.tf updated")

    # Upload back to MinIO
        print("📤 Uploading updated folder to MinIO...")
        for root, _, files in os.walk(download_path):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, download_path)
                object_key = f"{folder_name}/{relative_path}"
                minio_client.fput_object(bucket_name, object_key, file_path)
                print(f"⬆️  {file_path} -> {object_key}")

        print("✅ Upload complete")

        return f"""
        ✅ Terraform file updated and synced to MinIO.
        {updated_code}
        """
    except S3Error as s3e:
        raise Exception(f"❌ MinIO error: {str(s3e)}")
    except Exception as e:
        raise Exception(f"❌ Update failed: {str(e)}")
    finally:
        # Cleanup temporary folder
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"🧹 Deleted temp directory: {temp_dir}")


@tool
def apply_terraform_tool_local(project_name: str, config: RunnableConfig) -> str:
    """
    Downloads a Terraform project folder from MinIO, injects AWS credentials if needed,
    runs `terraform apply`, and uploads the updated folder back to MinIO.
    """
    print("🚀 Running apply_terraform_tool_local with project:", project_name)

    user_id = config['configurable'].get('user_id', 'unknown')
    bucket_name = f"terraform-workspaces-user-{user_id}"
    folder_name = f"{project_name}_terraform"

    # Temporary local working directory
    temp_dir = tempfile.mkdtemp()
    local_tf_dir = os.path.join(temp_dir, folder_name)
    os.makedirs(local_tf_dir, exist_ok=True)

    try:
        # MinIO Client
        minio_client = Minio(
            "storage.clouvix.com",
            access_key="clouvix@gmail.com",
            secret_key="Clouvix@bangalore2025",
            secure=True
        )

        # Download all project files from MinIO
        print(f"📥 Downloading Terraform project `{folder_name}` from bucket `{bucket_name}`...")
        objects = minio_client.list_objects(bucket_name, prefix=f"{folder_name}/", recursive=True)
        for obj in objects:
            object_key = obj.object_name
            relative_path = object_key[len(folder_name) + 1:]
            local_path = os.path.join(local_tf_dir, relative_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            minio_client.fget_object(bucket_name, object_key, local_path)
            print(f"⬇️  {object_key} -> {local_path}")

        terraform_file_path = os.path.join(local_tf_dir, "main.tf")
        if not os.path.exists(terraform_file_path):
            raise FileNotFoundError("❌ Terraform file not found in downloaded folder")

        # Fetch AWS credentials from DB
        db: Session = next(get_db())
        connections = get_user_connections_by_type(db, user_id, "aws")
        if not connections:
            raise ValueError("❌ No AWS connection found for user")

        connection = connections[0]
        connection_data = json.loads(connection.connection_json)
        aws_access_key = next((item["value"] for item in connection_data if item["key"] == "AWS_ACCESS_KEY_ID"), None)
        aws_secret_key = next((item["value"] for item in connection_data if item["key"] == "AWS_SECRET_ACCESS_KEY"), None)

        if not aws_access_key or not aws_secret_key:
            raise ValueError("❌ AWS credentials are incomplete")
        print("State file exists or not")
        print(os.path.exists(os.path.join(local_tf_dir, "terraform.tfstate")))
        is_first_run = not os.path.exists(os.path.join(local_tf_dir, "terraform.tfstate"))
        print(is_first_run)
        if is_first_run:
            with open(terraform_file_path, "r") as file:
                tf_content = file.read()

            # Remove existing AWS provider block entirely
            tf_content = re.sub(
                r'provider\s+"aws"\s*{[^}]*}',  # match entire block
                '', tf_content, flags=re.DOTALL
            )

            # Add fresh AWS provider block with credentials
            provider_block = f'''
            provider "aws" {{
            access_key = "{aws_access_key}"
            secret_key = "{aws_secret_key}"
            region     = "us-east-1"
            }}
            '''

            tf_content = provider_block.strip() + "\n\n" + tf_content.strip()

            with open(terraform_file_path, "w") as file:
                file.write(tf_content)

            print("🔧 Replaced/injected AWS provider block (first run)")
        else:
            print("🟡 Skipping provider block injection (not first run)")

        # Run terraform init
        print("🔨 Running terraform init")
        subprocess.run(["terraform", "init"], cwd=local_tf_dir, check=True)

        # Run terraform apply
        print("🚀 Running terraform apply")
        result = subprocess.run(
            ["terraform", "apply", "-auto-approve"],
            cwd=local_tf_dir,
            capture_output=True,
            text=True
        )
        print(result)

        # Upload updated files to MinIO
        print("📤 Uploading updated folder back to MinIO...")
        for root, _, files in os.walk(local_tf_dir):
            for file in files:
                if ".terraform" in root:
                    continue
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, local_tf_dir)
                object_key = f"{folder_name}/{relative_path}"
                minio_client.fput_object(bucket_name, object_key, file_path)
                print(f"⬆️  {file_path} -> {object_key}")

        # Format and return result
        if result.returncode == 0:
            return f"""✅ Terraform Apply Successful for `{project_name}`
            ```bash
            {result.stdout}
            """ 
        else: return f"""❌ Terraform Apply Failed for {project_name}
            {result.stderr}
            """

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Terraform apply failed: {str(e)}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"🧹 Deleted local working directory: {temp_dir}")
    # except subprocess.CalledProcessError as e:
    #     return f"❌ Terraform CLI Error:\n```\n{e.stderr}\n```"
    # except Exception as e:
    #     return f"❌ Unexpected Error:\n```\n{str(e)}\n```"


@tool
def read_terraform_files_from_bucket(project_name: str, config: RunnableConfig) -> str:
    """
    Reads all files in the given Terraform project folder from MinIO and returns their contents for user to understand what they can modify.

    Args:
        project_name (str): Name of the Terraform project (e.g., "myproject")
        config (RunnableConfig): Contains user_id in config['configurable']

    Returns:
        str: Markdown-formatted string containing the contents of each file in the folder.
    """
    print("📖 Reading files from MinIO for project:", project_name)

    user_id = config['configurable'].get('user_id', 'unknown')
    bucket_name = f"terraform-workspaces-user-{user_id}"
    folder_name = f"{project_name}_terraform"

    # Temp directory to download files
    temp_dir = tempfile.mkdtemp()
    download_path = os.path.join(temp_dir, folder_name)
    os.makedirs(download_path, exist_ok=True)

    try:
        # Initialize MinIO client
        minio_client = Minio(
            "storage.clouvix.com",
            access_key="clouvix@gmail.com",
            secret_key="Clouvix@bangalore2025",
            secure=True
        )

        # Download files from folder
        print(f"📥 Downloading files from bucket: {bucket_name}, prefix: {folder_name}/")
        files_found = False
        for obj in minio_client.list_objects(bucket_name, prefix=f"{folder_name}/", recursive=True):
            object_key = obj.object_name
            relative_path = object_key[len(folder_name) + 1:]
            local_path = os.path.join(download_path, relative_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            minio_client.fget_object(bucket_name, object_key, local_path)
            print(f"⬇️  {object_key} -> {local_path}")
            files_found = True

        if not files_found:
            return f"❌ No files found in `{folder_name}/` of bucket `{bucket_name}`."

        # Read and format all files
        output = f"# 📁 Contents of `{project_name}_terraform`:\n"
        for root, _, files in os.walk(download_path):
            for filename in files:
                filepath = os.path.join(root, filename)
                relative_path = os.path.relpath(filepath, download_path)
                try:
                    with open(filepath, "r") as f:
                        content = f.read()
                except Exception as e:
                    content = f"⚠️ Could not read file: {e}"

                output += f"\n## 📄 `{relative_path}`\n```hcl\n{content.strip()}\n```\n"
        final_output = f"""
            # 📁 Terraform Workspace: `{project_name}_terraform`

            {output}

            You can now view and update this configuration or proceed to apply it.
            """
        print(final_output)
        return final_output

    except S3Error as e:
        return f"❌ MinIO error: {str(e)}"
    except Exception as e:
        return f"❌ Unexpected error: {str(e)}"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"🧹 Deleted temp directory: {temp_dir}")


@tool
def destroy_terraform_tool_local(project_name: str, config: RunnableConfig) -> str:
    """
    Downloads a Terraform project folder from MinIO, injects AWS credentials if needed,
    runs `terraform destroy`, and uploads the updated folder back to MinIO.
    """
    print("🧨 Running destroy_terraform_tool_local with project:", project_name)

    user_id = config['configurable'].get('user_id', 'unknown')
    bucket_name = f"terraform-workspaces-user-{user_id}"
    folder_name = f"{project_name}_terraform"

    # Temporary local working directory
    temp_dir = tempfile.mkdtemp()
    local_tf_dir = os.path.join(temp_dir, folder_name)
    os.makedirs(local_tf_dir, exist_ok=True)

    try:
        # MinIO Client
        minio_client = Minio(
            "storage.clouvix.com",
            access_key="clouvix@gmail.com",
            secret_key="Clouvix@bangalore2025",
            secure=True
        )

        # Download all project files from MinIO
        print(f"📥 Downloading Terraform project `{folder_name}` from bucket `{bucket_name}`...")
        objects = minio_client.list_objects(bucket_name, prefix=f"{folder_name}/", recursive=True)
        for obj in objects:
            object_key = obj.object_name
            relative_path = object_key[len(folder_name) + 1:]
            local_path = os.path.join(local_tf_dir, relative_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            minio_client.fget_object(bucket_name, object_key, local_path)
            print(f"⬇️  {object_key} -> {local_path}")

        terraform_file_path = os.path.join(local_tf_dir, "main.tf")
        if not os.path.exists(terraform_file_path):
            raise FileNotFoundError("❌ Terraform file not found in downloaded folder")

        # Fetch AWS credentials from DB
        db: Session = next(get_db())
        connections = get_user_connections_by_type(db, user_id, "aws")
        if not connections:
            raise ValueError("❌ No AWS connection found for user")

        connection = connections[0]
        connection_data = json.loads(connection.connection_json)
        aws_access_key = next((item["value"] for item in connection_data if item["key"] == "AWS_ACCESS_KEY_ID"), None)
        aws_secret_key = next((item["value"] for item in connection_data if item["key"] == "AWS_SECRET_ACCESS_KEY"), None)

        if not aws_access_key or not aws_secret_key:
            raise ValueError("❌ AWS credentials are incomplete")

        # Inject AWS provider block if needed - commented
        # with open(terraform_file_path, "r") as file:
        #     tf_content = file.read()

        # if 'provider "aws"' not in tf_content:
        #     provider_block = f'''
        #         provider "aws" {{
        #         access_key = "{aws_access_key}"
        #         secret_key = "{aws_secret_key}"
        #         region     = "us-east-1"
        #         }}
        #         '''
        #     tf_content = provider_block + "\n" + tf_content
        #     with open(terraform_file_path, "w") as file:
        #         file.write(tf_content)
        #     print("🔧 Injected AWS provider block")

        # Run terraform init
        print("🔨 Running terraform init")
        subprocess.run(["terraform", "init"], cwd=local_tf_dir, check=True)

        # Run terraform apply
        print("💣 Running terraform destroy")
        result = subprocess.run(
            ["terraform", "destroy", "-auto-approve"],
            cwd=local_tf_dir,
            capture_output=True,
            text=True
        )

        print(result)
        # Upload updated files to MinIO
        print("📤 Uploading updated folder back to MinIO...")
        for root, _, files in os.walk(local_tf_dir):
            for file in files:
                if ".terraform" in root:
                    continue

                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, local_tf_dir)
                object_key = f"{folder_name}/{relative_path}"
                minio_client.fput_object(bucket_name, object_key, file_path)
                print(f"⬆️  {file_path} -> {object_key}")

        # Format and return result
        if result.returncode == 0:
            return f"""
        ✅ Terraform Apply Successful for `{project_name}`

        ```bash
        {result.stdout.strip()}
        ```
        """
        else: return f""" ❌ Terraform Apply Failed for {project_name}
        {result.stderr.strip()}
        """

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Terraform apply failed: {str(e)}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"🧹 Deleted local working directory: {temp_dir}")
    # except subprocess.CalledProcessError as e:
    #     return f"❌ Terraform CLI Error:\n```\n{e.stderr}\n```"
    # except Exception as e:
    #     return f"❌ Unexpected Error:\n```\n{str(e)}\n```"

@tool
def validate_and_fix_terraform_tool(project_name: str, config: RunnableConfig) -> str:
    """
    Validates Terraform files
    Downloads Terraform project folder from MinIO, validates and fixes main.tf using OpenAI and API loop,
    uploads the updated folder back to MinIO, and returns the final validated main.tf.
    """
    print(f"🔍 Running validate_and_fix_terraform_tool for: {project_name}")

    user_id = config['configurable'].get('user_id', 'unknown')
    bucket_name = f"terraform-workspaces-user-{user_id}"
    folder_name = f"{project_name}_terraform"

    temp_dir = tempfile.mkdtemp()
    local_tf_dir = os.path.join(temp_dir, folder_name)
    os.makedirs(local_tf_dir, exist_ok=True)

    try:
        # Initialize MinIO
        minio_client = Minio(
            "storage.clouvix.com",
            access_key="clouvix@gmail.com",
            secret_key="Clouvix@bangalore2025",
            secure=True
        )

        print(f"📥 Downloading Terraform files from {bucket_name}/{folder_name}/")
        for obj in minio_client.list_objects(bucket_name, prefix=f"{folder_name}/", recursive=True):
            object_key = obj.object_name
            relative_path = object_key[len(folder_name) + 1:]
            local_path = os.path.join(local_tf_dir, relative_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            minio_client.fget_object(bucket_name, object_key, local_path)
            print(f"⬇️  {object_key} -> {local_path}")

        terraform_file_path = os.path.join(local_tf_dir, "main.tf")
        if not os.path.exists(terraform_file_path):
            raise FileNotFoundError("❌ Terraform file not found.")

        with open(terraform_file_path, "r") as f:
            terraform_code = f.read()

        # Run validation + fix loop
        attempt = 0
        while True:
            attempt += 1
            print(f"🔄 Validation Attempt {attempt}")

            with open(terraform_file_path, "w") as tf_file:
                tf_file.write(terraform_code)

            success, error_message = validate_terraform_api(terraform_file_path)
            if success:
                print("✅ Terraform validation successful.")
                break

            print(f"🛠️ Fixing error: {error_message}")
            terraform_code = fix_terraform_with_openai(terraform_code, error_message)

        # Upload updated folder to MinIO (skip `.terraform`)
        print("📤 Uploading updated folder to MinIO...")
        for root, _, files in os.walk(local_tf_dir):
            for file in files:
                if ".terraform" in root:
                    continue
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, local_tf_dir)
                object_key = f"{folder_name}/{relative_path}"
                minio_client.fput_object(bucket_name, object_key, file_path)
                print(f"⬆️  {file_path} -> {object_key}")

        # Return final validated main.tf
        return f"""
            ✅ Terraform file validated and updated for `{project_name}`

            ```hcl
            {terraform_code.strip()}
            ```
            """ 
    except Exception as e: raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"🧹 Deleted temp directory: {temp_dir}")