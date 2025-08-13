# from typing import Dict, Any
# from langchain_core.tools import tool
# from langchain_core.runnables import RunnableConfig
# from langchain_core.messages import SystemMessage, HumanMessage
# from langchain_openai import ChatOpenAI, OpenAIEmbeddings
# from sqlalchemy import text
# from minio import Minio
# from minio.error import S3Error
# import json
# import os
# import re
# import shutil
# import tempfile
# import datetime

# from pymongo import MongoClient

# # Import your database and workspace modules
# from app.database import get_db_session
# from app.schemas.workspace import WorkspaceCreate
# from app.db.workspace import create_workspace
# from app.models.workspace import Workspace

# # Configuration - Make sure these are set in your environment
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# MINIO_ENDPOINT = "storage.clouvix.com"
# MINIO_ACCESS_KEY = "clouvix@gmail.com"
# MINIO_SECRET_KEY = "Clouvix@bangalore2025"

# # Global variable for terraform directory
# TERRAFORM_DIR = ""

# # #Initialize your MongoDB collections 
# # ec2_collection = "ec2_resources"
# # s3_collection = "s3_resources"
# # rds_collection = "rds_resources"

# # MongoDB Configuration
# MONGODB_URI = os.getenv("MONGODB_URI")
# if not MONGODB_URI:
#     raise ValueError("MONGODB_URI environment variable is not set")

# # Initialize MongoDB client and database
# mongo_client = MongoClient(MONGODB_URI)

# db = mongo_client["terraform_embeddings"]

# # Initialize your MongoDB collections as actual collection objects
# ec2_collection = db["ec2_resources"]
# s3_collection = db["s3_resources"] 
# rds_collection = db["rds_resources"]


# @tool
# def generate_terraform_code(query: str, project_name: str, config: RunnableConfig) -> Dict:
#     """
#     Terraform code generator with DB lookup and storage for architecture diagrams.
    
#     Args:
#         query: The user query describing the infrastructure to create
#         project_name: Project name provided by the user. If not provided, will attempt to extract from query
#         config: Configuration containing user_id
#     """
#     # Extract user_id from config
#     user_id = config.get('configurable', {}).get('user_id', 'unknown')
#     if user_id == "unknown":
#         return {"success": False, "error": "User ID missing from configuration"}
    
#     # If project_name is not provided, try to extract it from the query using LLM
#     if not project_name:
#         extracted_project_name = _extract_project_name_from_query(query)
#         print(f"Extracted project name from query: {extracted_project_name}")
#         if extracted_project_name:
#             project_name = extracted_project_name
#             print(f"✅ Extracted project name from query: {project_name}")
#         else:
#             return {
#                 "success": False, 
#                 "error": "Project name not provided",
#                 "needs_project_name": True,
#                 "message": "Please provide a project name for your Terraform infrastructure. For example: 'my-webapp' or 'data-pipeline-project'"
#             }
    
#     print(f"\n🔍 Starting Terraform generation for project: {project_name}")
#     services_json = {}

#     try:
#         with get_db_session() as db:
#             result = db.execute(
#                 text("SELECT architecture_json FROM architecture WHERE userid = :userid AND project_name = :project_name"),
#                 {"userid": user_id, "project_name": project_name}
#             ).fetchone()

#             if result:
#                 print(f"✅ Found existing architecture in DB for user {user_id}, project {project_name}")
#                 # Make sure we're dealing with a dictionary, not a string
#                 if isinstance(result[0], str):
#                     services_json = json.loads(result[0])
#                 else:
#                     # If it's already a dict or other object, use it directly
#                     services_json = result[0]
#             else:
#                 print(f"⚙️ No architecture found. Parsing query...")
#                 services_json = _parse_services_and_connections(query)
#                 services_json["project_name"] = project_name

#                 result_check = db.execute(
#                     text("SELECT COUNT(*) FROM architecture WHERE userid = :userid AND project_name = :project_name"),
#                     {"userid": user_id, "project_name": project_name}
#                 ).fetchone()

#                 if result_check and result_check[0] > 0:
#                     return {
#                         "success": False,
#                         "error": f"Project name '{project_name}' already exists for this user. Please use a different project name."
#                     }

#                 db.execute(
#                     text("INSERT INTO architecture (userid, architecture_json, project_name) VALUES (:userid, :architecture_json, :project_name)"),
#                     {
#                         "userid": user_id,
#                         "architecture_json": json.dumps(services_json),
#                         "project_name": project_name
#                     }
#                 )
#                 db.commit()
#                 print(f"📝 Saved new architecture to DB for user {user_id}, project {project_name}")

#         # Collect documentation
#         docs = fetch_documentation_via_llm(query, services_json)
#         ec2_docs = docs.get("ec2", "")
#         s3_docs = docs.get("s3", "")
#         rds_docs = docs.get("rds", "")


#         # ec2_docs = s3_docs = rds_docs = ""
#         # service_types = [s.get("type", "").lower() for s in services_json.get("services", [])]

#         # if any("ec2" in s for s in service_types):
#         #     ec2_docs = get_ec2_documentation(query)
#         #     print(f"EC2 Documentation: {ec2_docs}")
#         # if any("s3" in s for s in service_types):
#         #     s3_docs = get_s3_documentation(query)
#         #     print(f"S3 Documentation: {s3_docs}")
#         # if any("rds" in s for s in service_types):
#         #     rds_docs = get_rds_documentation(query)
#         #     print(f"RDS Documentation: {rds_docs}")

#         # Create numbered terraform folder
#         terraform_dir = get_terraform_folder(project_name)
#         global TERRAFORM_DIR
#         TERRAFORM_DIR = terraform_dir
        
#         os.makedirs(TERRAFORM_DIR, exist_ok=True)
#         print(f"Created Terraform directory: {TERRAFORM_DIR}")

#         print("\n🔨 Generating Terraform code...")
#         terraform_code = _generate_terraform_hcl(
#             query=query,
#             ec2_docs=ec2_docs,
#             s3_docs=s3_docs,
#             rds_docs=rds_docs,
#             services_json=services_json
#         )

#         # Extract and Save Terraform File
#         try:
#             extract_and_save_terraform(
#                 terraform_output=terraform_code,
#                 services=services_json.get("services", []),
#                 connections=services_json.get("connections", []),
#                 user_id=user_id,
#                 project_name=project_name,
#                 services_json=services_json
#             )
#             print(f"Successfully saved Terraform file to {TERRAFORM_DIR}/main.tf")
#         except Exception as e:
#             error_msg = f"Error saving Terraform file: {str(e)}"
#             print(error_msg)
#             return {"success": False, "error": error_msg}

#         # Read the generated Terraform file
#         try:
#             with open(os.path.join(TERRAFORM_DIR, "main.tf"), "r") as f:
#                 terraform_content = f.read()
#         except Exception as e:
#             error_msg = f"Error reading generated Terraform file: {str(e)}"
#             print(error_msg)
#             return {"success": False, "error": error_msg}

#         print("📤 Uploading Terraform directory to MinIO...")

#         # Upload to MinIO
#         try:
#             minio_client = Minio(
#                 MINIO_ENDPOINT,
#                 access_key=MINIO_ACCESS_KEY,
#                 secret_key=MINIO_SECRET_KEY,
#                 secure=True
#             )

#             bucket_name = f"terraform-workspaces-user-{user_id}"

#             # Create bucket if it doesn't exist
#             if not minio_client.bucket_exists(bucket_name):
#                 print("Inside Make bucket")
#                 minio_client.make_bucket(bucket_name)
#                 print(f"🪣 Created bucket: {bucket_name}")
#             else:
#                 print(f"📦 Bucket exists: {bucket_name}")

#             folder_name = os.path.basename(TERRAFORM_DIR.rstrip("/"))

#             # Upload each file with folder_name prefix
#             for root, _, files in os.walk(TERRAFORM_DIR):
#                 for file in files:
#                     file_path = os.path.join(root, file)
#                     relative_path = os.path.relpath(file_path, TERRAFORM_DIR)
#                     object_key = f"{folder_name}/{relative_path}"
#                     print(f"⬆️ Uploading: {file_path} -> {object_key}")
#                     minio_client.fput_object(bucket_name, object_key, file_path)

#             print("✅ Terraform directory uploaded to MinIO!")

#         except Exception as e:
#             print(f"❌ Error uploading to MinIO: {e}")
#             # Continue execution even if MinIO upload fails

#         # Clean up local directory
#         try:
#             shutil.rmtree(TERRAFORM_DIR)
#             print(f"🧹 Deleted local Terraform directory: {TERRAFORM_DIR}")
#         except Exception as e:
#             print(f"⚠️ Failed to delete local Terraform directory: {e}")

#         # return {
#         #     "success": True,
#         #     "terraform_code": terraform_content,
#         #     "message": "Terraform configuration generated successfully. You can now proceed with adding user inputs required for this Terraform configuration and then proceed with applying."
#         # }
#         return {terraform_content}

#     except Exception as e:
#         error_msg = f"Error in generate_terraform_code: {str(e)}"
#         print(error_msg)
#         return {"success": False, "error": error_msg}


# def get_terraform_folder(project_name: str) -> str:
#     """Create a numbered terraform folder based on project name"""
#     base_folder = f"{project_name}_terraform"
#     folder = base_folder
#     counter = 1
    
#     while os.path.exists(folder):
#         folder = f"{project_name}_{counter}_terraform"
#         counter += 1
        
#     return folder


# def extract_and_save_terraform(terraform_output, services, connections, user_id, project_name, services_json):
#     """Extracts Terraform configurations, validates, fixes errors, and saves the final file."""
#     if not terraform_output:
#         print("Error: No Terraform code generated.")
#         return

#     terraform_output = re.sub(r"```hcl|```", "", terraform_output).strip()

#     # Create terraform directory if it doesn't exist
#     if not os.path.exists(TERRAFORM_DIR):
#         os.makedirs(TERRAFORM_DIR, exist_ok=True)
#         print(f"Created Terraform directory: {TERRAFORM_DIR}")

#     # Validate and Fix Terraform Configuration
#     validated_code = validate_terraform_with_openai(terraform_output, services_json)

#     # Save the final validated Terraform file
#     final_tf_path = os.path.join(TERRAFORM_DIR, "main.tf")
#     with open(final_tf_path, "w") as tf_file:
#         tf_file.write(validated_code)

#     # Add an entry to workspace table
#     try:
#         with get_db_session() as db:
#             # Ensure services_json is a dictionary for the WorkspaceCreate model
#             if isinstance(services_json, str):
#                 try:
#                     diagramjson_dict = json.loads(services_json)
#                 except json.JSONDecodeError:
#                     print("Error parsing services_json as JSON string")
#                     diagramjson_dict = {"error": "Failed to parse JSON"}
#             else:
#                 # If it's already a dict, use it directly
#                 diagramjson_dict = services_json
            
#             new_workspace = WorkspaceCreate(
#                 userid=user_id,
#                 wsname=project_name,
#                 filetype="terraform",
#                 filelocation=final_tf_path,
#                 diagramjson=diagramjson_dict,
#                 githublocation=""
#             )
#             create_workspace(db=db, workspace=new_workspace)
#             print(f"\n✅ Final validated Terraform file saved at: {final_tf_path}")
#     except Exception as e:
#         print(f"Error saving to workspace: {e}")


# def _parse_services_and_connections(query: str) -> Dict[str, Any]:
#     """Parse the user query to identify AWS services and their connections."""
#     try:
#         prompt = """
# You are an expert at analyzing infrastructure requirements from text descriptions.

# Task: Parse the given user query to identify:
# 1. Project name (generate a simple one if not specified)
# 2. AWS services mentioned (EC2, S3, RDS, Lambda, etc.)
# 3. Connections between these services (which services need to interact)

# Return ONLY a valid JSON object with this EXACT structure:
# {
#   "project_name": "string",
#   "services": [
#     {
#       "id": "timestamp-randomstring",
#       "type": "service_type",
#       "label": "Service Label",
#       "githubRepo": ""
#     }
#   ],
#   "connections": [
#     {
#       "from_": "service_type1",
#       "to": "service_type2"
#     }
#   ]
# }

# IMPORTANT RULES:
# - Use lowercase service types (ec2, s3, rds, lambda, etc.)
# - Generate unique IDs with format: timestamp-randomstring (e.g., "1751377886288-bbhokwtx8")
# - Always include "githubRepo": "" (empty string) for each service
# - Use proper service labels: "EC2 Instance", "S3 Bucket", "AWS RDS", "Lambda Function", etc.
# - Infer logical connections based on typical AWS architecture patterns
# - If no connections are obvious, make intelligent assumptions based on services mentioned

# Example output format:
# {
#   "project_name": "web-app-project",
#   "services": [
#     {
#       "id": "1751377886288-bbhokwtx8",
#       "type": "ec2",
#       "label": "EC2 Instance",
#       "githubRepo": ""
#     },
#     {
#       "id": "1751377887375-c7tpua7hc",
#       "type": "s3",
#       "label": "S3 Bucket",
#       "githubRepo": ""
#     }
#   ],
#   "connections": [
#     {
#       "from_": "ec2",
#       "to": "s3"
#     }
#   ]
# }
# """

#         messages = [
#             SystemMessage(content=prompt),
#             HumanMessage(content=f"User Query: {query}")
#         ]

#         llm = ChatOpenAI(model="gpt-4o", temperature=0.1, api_key=OPENAI_API_KEY)
#         response = llm.invoke(messages)
        
#         # Extract JSON from response
#         content = response.content.strip()
        
#         # Try to find JSON in the response
#         json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
#         if json_match:
#             json_str = json_match.group(1)
#         else:
#             # If no JSON block, try to parse the whole content
#             json_str = content
        
#         # Clean up any non-JSON text
#         json_str = re.sub(r'^[^{]*', '', json_str)
#         json_str = re.sub(r'[^}]*$', '', json_str)

#         # Parse JSON
#         try:
#             parsed_json = json.loads(json_str)
#             return parsed_json
#         except json.JSONDecodeError as e:
#             print(f"Error parsing JSON: {e}")
#             # Return a default structure
#             return {
#                 "project_name": "default-project",
#                 "services": [],
#                 "connections": []
#             }
            
#     except Exception as e:
#         print(f"Error in _parse_services_and_connections: {e}")
#         return {
#             "project_name": "default-project",
#             "services": [],
#             "connections": []
#         }


# def get_ec2_documentation(query: str) -> str:
#     """Retrieve EC2-related documentation."""
#     try:
#         model = OpenAIEmbeddings(model="text-embedding-3-large", openai_api_key=OPENAI_API_KEY)
#         query_vector = model.embed_query(query)
#         results = list(ec2_collection.aggregate([
#             {
#                 "$vectorSearch": {
#                     "index": "ec2_vector_index",
#                     "queryVector": query_vector,
#                     "path": "embeddings",
#                     "numCandidates": 50,
#                     "limit": 1,
#                     "similarity": "cosine"
#                 }
#             }
#         ]))
#         if results:
#             return results[0].get("combined_text", "No result found.")
#         else:
#             return "No EC2 result found."
        
#     except Exception as e:
#         print(f"Error in get_ec2_documentation: {e}")
#         return f"Error retrieving EC2 documentation: {str(e)}"


# def get_s3_documentation(query: str) -> str:
#     """Retrieve S3-related documentation."""
#     try:
#         model = OpenAIEmbeddings(model="text-embedding-3-large", openai_api_key=OPENAI_API_KEY)
#         query_vector = model.embed_query(query)
#         results = list(s3_collection.aggregate([
#             {
#                 "$vectorSearch": {
#                     "index": "s3_vector_index",
#                     "queryVector": query_vector,
#                     "path": "embeddings",
#                     "numCandidates": 50,
#                     "limit": 1,
#                     "similarity": "cosine"
#                 }
#             }
#         ]))
#         if results:
#             return results[0].get("combined_text", "No result found.")
#         else:
#             return "No S3 result found."
#     except Exception as e:
#         print(f"Error in get_s3_documentation: {e}")
#         return f"Error retrieving S3 documentation: {str(e)}"


# def get_rds_documentation(query: str) -> str:
#     """Retrieve RDS-related documentation."""
#     try:
#         model = OpenAIEmbeddings(model="text-embedding-3-large", openai_api_key=OPENAI_API_KEY)
#         query_vector = model.embed_query(query)
#         results = list(rds_collection.aggregate([
#             {
#                 "$vectorSearch": {
#                     "index": "rds_vector_index",
#                     "queryVector": query_vector,
#                     "path": "embeddings",
#                     "numCandidates": 50,
#                     "limit": 1,
#                     "similarity": "cosine"
#                 }
#             }
#         ]))
#         if results:
#             return results[0].get("combined_text", "No result found.")
#         else:
#             return "No RDS result found."
#     except Exception as e:
#         print(f"Error in get_rds_documentation: {e}")
#         return f"Error retrieving RDS documentation: {str(e)}"


# def _generate_terraform_hcl(query: str, ec2_docs: str = "", s3_docs: str = "", rds_docs: str = "", services_json: dict = None) -> str:
#     """Generate Terraform HCL code based on the query and documentation."""
#     try:
#         # Extract project details from services_json
#         project_name = ""
#         service_details = {}
#         user_connections = []
        
#         if services_json:
#             # Extract project name
#             project_name = services_json.get("project_name", "")
            
#             # Extract service details
#             services = services_json.get("services", [])
#             service_details = {
#                 "services": services,
#                 "total_services": len(services)
#             }
            
#             # Extract connections
#             connections = services_json.get("connections", [])
#             user_connections = connections
            
#             # Debug prints
#             print(f"Project Name: {project_name}")
#             print("\n===== SERVICE DETAILS =====\n")
#             print(json.dumps(service_details, indent=2))
#             print("\n===== USER CONNECTIONS =====\n")
#             print(json.dumps(user_connections, indent=2))
        
#         prompt = """
# You are a Terraform code generator. Use the following rules:
# ONLY output valid HCL Terraform code. Never apologize or mention error handling.
# Avoid all explanatory or fallback language.
# Follow below rules compulsorily:
# - Focus on the **Argument Reference** section for required arguments.
# - Add optional arguments only if they're mentioned or implied in the user query.
# - Strictly ignore the **Example Usage** section. Just use the argument reference and syntax and create terraform file according to user query.
# - From user query understand the requirement of the user which service is need to be connected with other service.And then take care of all the roles and policies and permissions and all the other things.
# - Return only Terraform HCL code, no explanation.
# - Do not use deprecated input parameters strictly.
# - Assume AWS region is 'us-east-1' unless stated otherwise.
# - Generate secure, minimal, and production-ready Terraform code.
# - Always include provider block.
# - IMPORTANT: If services_json is provided, strictly follow the connections specified in it when creating resources.
# - Use meaningful and unique resource names based on the project name provided.
# - Ensure all IAM roles, policies, and security groups are properly configured for the specified connections.
#         """
        
#         # Build context with enhanced project information
#         context = f"User Request: {query}\n\n"
        
#         if project_name:
#             context += f"Project Name: {project_name}\n"
#             context += f"- **Use my project name: `{project_name}`** to generate unique and meaningful names for Terraform resources.\n\n"
        
#         if ec2_docs:
#             context += f"EC2 Documentation:\n{ec2_docs}\n\n"
#         if s3_docs:
#             context += f"S3 Documentation:\n{s3_docs}\n\n"
#         if rds_docs:
#             context += f"RDS Documentation:\n{rds_docs}\n\n"
            
#         if services_json:
#             context += f"Architecture JSON:\n{json.dumps(services_json, indent=2)}\n\n"
#             context += f"Services and Connections JSON:\n{json.dumps(service_details, indent=2)}\n\n"
#             context += f"User Connections:\n{json.dumps(user_connections, indent=2)}\n\n"
#             context += "IMPORTANT: Follow the connections specified in the JSON above when creating resources. Make sure to implement all the necessary IAM roles, policies, and permissions to enable these connections.\n"
#             context += f"Use the project name '{project_name}' as a prefix or suffix for all resource names to ensure uniqueness.\n\n"
        
#         messages = [
#             SystemMessage(content=prompt),
#             HumanMessage(content=context)
#         ]
#         print(f"Messages: {messages}")

#         chat_llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=OPENAI_API_KEY)
#         response = chat_llm.invoke(messages)
#         content = response.content.strip()
        
#         # Extract code from markdown blocks if present
#         if "```" in content:
#             code_blocks = re.findall(r"```(?:hcl|terraform)?\n(.*?)```", content, re.DOTALL)
#             if code_blocks:
#                 return code_blocks[0].strip()
        
#         return content
        
#     except Exception as e:
#         print(f"Error in _generate_terraform_hcl: {e}")
#         return f"# Error generating Terraform code: {str(e)}"


# def validate_terraform_with_openai(terraform_code, architecture_json):
#     """Validate and fix Terraform code using OpenAI."""
#     try:
#         # Ensure architecture_json is a dictionary
#         if isinstance(architecture_json, str):
#             try:
#                 architecture_json = json.loads(architecture_json)
#             except json.JSONDecodeError:
#                 print("Error parsing architecture_json as JSON string")
#                 return terraform_code
                
#         services = architecture_json.get("services", [])
#         connections = architecture_json.get("connections", [])

#         # Convert services and connections to dict if they're not already
#         services_dict = []
#         for service in services:
#             if hasattr(service, 'dict'):
#                 services_dict.append(service.dict())
#             elif isinstance(service, dict):
#                 services_dict.append(service)
#             else:
#                 services_dict.append(str(service))

#         connections_dict = []
#         for conn in connections:
#             if hasattr(conn, 'dict'):
#                 connections_dict.append(conn.dict())
#             elif isinstance(conn, dict):
#                 connections_dict.append(conn)
#             else:
#                 connections_dict.append(str(conn))

#         llm = ChatOpenAI(model="gpt-4o", temperature=0.1, api_key=OPENAI_API_KEY)

#         messages = [
#             SystemMessage(content="You are an expert Terraform engineer. Validate the Terraform file to ensure it meets the user's requirements."),
#             HumanMessage(content=f"""
#             The user wants to deploy the following AWS infrastructure:

#             **Services:**
#             ```json
#             {json.dumps(services_dict, indent=2)}
#             ```

#             **Connections:**
#             ```json
#             {json.dumps(connections_dict, indent=2)}
#             ```
#             Check if each connection is being handled properly, including IAM roles, policies, security groups, and networking for connecting required services.

#             **Terraform Configuration:**
#             ```hcl
#             {terraform_code}
#             ```

#             **Validation Request:**
#             - Does this Terraform file achieve the user's intended goal?
#             - If yes, return the entire Terraform file as is.
#             - If no, update it to align with the user's infrastructure requirements and return the complete corrected Terraform configuration.
#             - Ensure: Do NOT include function code, Docker image URLs, or any deployment-related configuration.
#             - The response should only contain valid Terraform HCL code, without explanations.
#             """)
#         ]

#         response = llm.invoke(messages)
#         validated_code = re.sub(r"```hcl|```", "", response.content.strip()).strip()

#         print("🔎 Running OpenAI validation for missing connections...")
#         messages = [
#             SystemMessage(content="You are an expert Terraform engineer. Validate that the Terraform file includes all required service connections."),
#             HumanMessage(content=f"""
#             The user wants the following service connections:

#             **Connections:**
#             ```json
#             {json.dumps(connections_dict, indent=2)}
#             ```

#             **Current Terraform Configuration:**
#             ```hcl
#             {validated_code}
#             ```

#             **Validation Request:**
#             - Ensure all the required connections between services are properly handled in the Terraform file.
#             - If any connection is missing, **ONLY add the missing connection** (e.g., security groups, IAM roles, networking rules, etc.).
#             - **DO NOT remove or modify any existing connections**.
#             - If all required connections are already present, return the Terraform file as it is.
#             - The response should contain only the entire valid Terraform HCL file without explanations.
#             """)
#         ]

#         response = llm.invoke(messages)
#         final_code = re.sub(r"```hcl|```", "", response.content.strip()).strip()

#         return final_code

#     except Exception as e:
#         print(f"Error in validate_terraform_with_openai: {e}")
#         return terraform_code  # Return original code if validation fails


# # def _create_services_summary(services_json: dict) -> str:
# #     """Create a human-readable summary of the services and connections."""
# #     try:
# #         summary = []
        
# #         # Project name
# #         project_name = services_json.get("project_name", "Unnamed Project")
# #         summary.append(f"🔶 Project: {project_name}")
        
# #         # Services
# #         services = services_json.get("services", [])
# #         if services:
# #             summary.append("\n🔷 Services:")
# #             for service in services:
# #                 label = service.get('label', 'Unknown')
# #                 service_type = service.get('type', 'unknown')
# #                 summary.append(f"  • {label} ({service_type})")
# #         else:
# #             summary.append("\n🔷 Services: None identified")
        
# #         # Connections
# #         connections = services_json.get("connections", [])
# #         summary.append("\n🔗 Connections:")
# #         if connections:
# #             for conn in connections:
# #                 from_service = conn.get('from_', 'unknown')
# #                 to_service = conn.get('to', 'unknown')
# #                 summary.append(f"  • {from_service} → {to_service}")
# #         else:
# #             summary.append("  • No connections defined")
        
# #         return "\n".join(summary)
        
# #     except Exception as e:
# #         return f"Error creating summary: {str(e)}"


# def _extract_project_name_from_query(query: str) -> str:
#     """
#     Use LLM to intelligently extract project name from the user query.
    
#     Args:
#         query: The user query about Terraform infrastructure
        
#     Returns:
#         str: The extracted project name or None if not found
#     """
#     try:
#         prompt = """
# You are an AI assistant that extracts project names from user queries about Terraform infrastructure.

# INSTRUCTIONS:
# 1. Analyze the user query and identify if it contains a project name
# 2. Look for phrases like "project name is X", "for project X", "named X", etc.
# 3. If you find a project name, return ONLY the project name as a single word or hyphenated phrase
# 4. If no project name is mentioned, return "None"

# IMPORTANT:
# - Return ONLY the project name or "None" - no other text
# - Project names should be alphanumeric with optional hyphens or underscores
# - Do not include quotes or other punctuation in the project name
# - Do not explain your reasoning

# EXAMPLES:
# Query: "Generate terraform code for an EC2 instance for project my-webapp"
# Response: my-webapp

# Query: "Create S3 bucket with the project name test_project"
# Response: test_project

# Query: "I need terraform for a lambda function"
# Response: None
# """

#         messages = [
#             SystemMessage(content=prompt),
#             HumanMessage(content=query)
#         ]

#         llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=OPENAI_API_KEY)
#         response = llm.invoke(messages)
        
#         # Extract the project name from the response
#         project_name = response.content.strip()
        
#         # Return None if the LLM couldn't find a project name
#         if project_name.lower() == "none":
#             return None
            
#         return project_name
        
#     except Exception as e:
#         print(f"Error extracting project name with LLM: {e}")
#         return None

# def fetch_documentation_via_llm(query: str, services_json: dict) -> Dict[str, str]:
#     """
#     Uses LLM to analyze the user query and services_json to:
#     1. Generate keyword-like subqueries for each service type.
#     2. Decide which MongoDB fetch functions to call.
#     3. Collect and return service documentation.

#     Returns:
#         dict: Dictionary with service type as keys (ec2, s3, rds) and documentation as values.
#     """
#     try:
#         prompt = """
# You are an expert AI assistant that:
# 1. Analyzes the user query and architecture_json (services + connections)
# 2. Determines which AWS services (ec2, s3, rds) are required
# 3. For each service, generate a keyword-focused query to pass to a MongoDB vector search
# 4. Return a JSON with structure:
# {
#   "ec2": "subquery for ec2",
#   "s3": "subquery for s3",
#   "rds": "subquery for rds"
# }
# If a service is not needed, set its value to null.
# IMPORTANT: Only return JSON, no explanation.
#         """

#         messages = [
#             SystemMessage(content=prompt),
#             HumanMessage(content=f"User Query: {query}\n\nArchitecture JSON:\n{json.dumps(services_json, indent=2)}")
#         ]

#         llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=OPENAI_API_KEY)
#         response = llm.invoke(messages)

#         # Extract and parse JSON from the response
#         json_str = re.sub(r'^.*?\{', '{', response.content.strip(), flags=re.DOTALL)
#         json_str = re.sub(r'\}.*$', '}', json_str, flags=re.DOTALL)
#         subquery_map = json.loads(json_str)

#         documentation = {
#             "ec2": "",
#             "s3": "",
#             "rds": ""
#         }

#         if subquery_map.get("ec2"):
#             documentation["ec2"] = get_ec2_documentation(subquery_map["ec2"])
#             print(f"EC2 Docs: {documentation['ec2']}")
#             print(f"EC2 Subquery: {subquery_map['ec2']}")
#         if subquery_map.get("s3"):
#             documentation["s3"] = get_s3_documentation(subquery_map["s3"])
#             print(f"S3 Docs: {documentation['s3']}")
#             print(f"S3 Subquery: {subquery_map['s3']}")
#         if subquery_map.get("rds"):
#             documentation["rds"] = get_rds_documentation(subquery_map["rds"])
#             print(f"RDS Docs: {documentation['rds']}")
#             print(f"RDS Subquery: {subquery_map['rds']}")   
#         return documentation

#     except Exception as e:
#         print(f"Error in fetch_documentation_via_llm: {e}")
#         return {
#             "ec2": "",
#             "s3": "",
#             "rds": ""
#         }



from typing import Dict, Any
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from sqlalchemy import text
from minio import Minio
from minio.error import S3Error
import json
import os
import re
import shutil
import tempfile
import datetime
import boto3
from app.models.connection import Connection

from pymongo import MongoClient

# Import your database and workspace modules
from app.database import get_db_session
from app.schemas.workspace import WorkspaceCreate
from app.db.workspace import create_workspace
from app.models.workspace import Workspace

# Configuration - Make sure these are set in your environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MINIO_ENDPOINT = "storage.clouvix.com"
MINIO_ACCESS_KEY = "clouvix@gmail.com"
MINIO_SECRET_KEY = "Clouvix@bangalore2025"

# Global variable for terraform directory
TERRAFORM_DIR = ""

# #Initialize your MongoDB collections 
# ec2_collection = "ec2_resources"
# s3_collection = "s3_resources"
# rds_collection = "rds_resources"

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set")

# Initialize MongoDB client and database
mongo_client = MongoClient(MONGODB_URI)

db = mongo_client["terraform_embeddings"]

# # Initialize your MongoDB collections as actual collection objects
# ec2_collection = db["ec2_resources"]
# s3_collection = db["s3_resources"] 
# rds_collection = db["rds_resources"]

# Collections (including new ones)
ec2_collection = db["ec2_resources"]
s3_collection = db["s3_resources"]
rds_collection = db["rds_resources"]
dynamodb_collection = db["dynamodb_cloudwatch_resources"]
apprunner_collection = db["apprunner_eks_ecs_resources"]
iam_collection = db["iam_resources"]
lambda_collection = db["lambda_resources"]
sagemaker_collection = db["sagemaker_bedrock_resources"]
sns_sqs_collection = db["sns_sqs_resources"]
vpc_collection = db["vpc_route53_api_gateway_resources"]


def get_s3_connection_info_with_credentials(user_id):
    """
    Fetches S3 backend info for Terraform remote state + AWS credentials.

    Returns:
        dict: {
            "bucket": str,
            "region": str,
            "prefix": str,
            "aws_access_key_id": str,
            "aws_secret_access_key": str
        }
    """
    result = {
        "bucket": None,
        "region": "us-east-1",
        "prefix": "",
        "aws_access_key_id": None,
        "aws_secret_access_key": None
    }

    with get_db_session() as db:
        # Fetch S3 remote state connection
        s3_conn = db.query(Connection).filter(
            Connection.userid == user_id,
            Connection.type == "aws_s3_remote_state"
        ).first()

        if not s3_conn:
            raise Exception("No S3 remote state connection found for user")

        s3_json = s3_conn.connection_json
        if isinstance(s3_json, str):
            try:
                s3_json = json.loads(s3_json)
            except json.JSONDecodeError:
                raise Exception("Invalid first-level JSON in S3 connection_json")
        if isinstance(s3_json, str):
            try:
                s3_json = json.loads(s3_json)
            except json.JSONDecodeError:
                raise Exception("Invalid second-level JSON in S3 connection_json")

        s3_info = {item["key"]: item["value"] for item in s3_json}
        result["bucket"] = s3_info.get("BUCKET_NAME")
        result["region"] = s3_info.get("AWS_REGION", result["region"])
        result["prefix"] = s3_info.get("PREFIX", result["prefix"])

        # Fetch AWS credentials
        aws_conn = db.query(Connection).filter(
            Connection.userid == user_id,
            Connection.type == "aws"
        ).first()

        if aws_conn:
            aws_json = aws_conn.connection_json
            if isinstance(aws_json, str):
                try:
                    aws_json = json.loads(aws_json)
                except json.JSONDecodeError:
                    raise Exception("Invalid first-level JSON in AWS connection_json")
            if isinstance(aws_json, str):
                try:
                    aws_json = json.loads(aws_json)
                except json.JSONDecodeError:
                    raise Exception("Invalid second-level JSON in AWS connection_json")

            aws_info = {item["key"]: item["value"] for item in aws_json}
            result["aws_access_key_id"] = aws_info.get("AWS_ACCESS_KEY_ID")
            result["aws_secret_access_key"] = aws_info.get("AWS_SECRET_ACCESS_KEY")
            # If region wasn't set in S3 config, take from credentials
            result["region"] = result["region"] or aws_info.get("AWS_REGION", result["region"])

    return result


def fetch_doc(collection, index, query):
    print(f"fetching doc for {index} with query: {query}")
    try:
        model = OpenAIEmbeddings(model="text-embedding-3-large", openai_api_key=OPENAI_API_KEY)
        query_vector = model.embed_query(query)
        results = list(collection.aggregate([{
            "$vectorSearch": {
                "index": index,
                "queryVector": query_vector,
                "path": "embeddings",
                "numCandidates": 50,
                "limit": 1,
                "similarity": "cosine"
            }
        }]))
        return results[0].get("combined_text", "No result found.") if results else f"No {index} result found."
    except Exception as e:
        return f"Error retrieving {index} documentation: {str(e)}"

@tool
def generate_terraform_code(query: str, project_name: str, config: RunnableConfig) -> Dict:
    """
    Terraform code generator with DB lookup, architecture parsing, and returns all .tf files.
    """
    user_id = config.get('configurable', {}).get('user_id', 'unknown')
    if user_id == "unknown":
        return {"success": False, "error": "User ID missing from configuration"}

    if not project_name:
        extracted_project_name = _extract_project_name_from_query(query)
        print(f"Extracted project name from query: {extracted_project_name}")
        if extracted_project_name:
            project_name = extracted_project_name
        else:
            return {
                "success": False,
                "error": "Project name not provided",
                "needs_project_name": True,
                "message": "Please provide a project name for your Terraform infrastructure. For example: 'my-webapp' or 'data-pipeline-project'"
            }

    print(f"\n🔍 Starting Terraform generation for project: {project_name}")
    services_json = {}

    try:
        with get_db_session() as db:
            result = db.execute(
                text("SELECT architecture_json FROM architecture WHERE userid = :userid AND project_name = :project_name"),
                {"userid": user_id, "project_name": project_name}
            ).fetchone()

            if result:
                services_json = json.loads(result[0]) if isinstance(result[0], str) else result[0]
            else:
                services_json = _parse_services_and_connections(query)
                services_json["project_name"] = project_name

                result_check = db.execute(
                    text("SELECT COUNT(*) FROM architecture WHERE userid = :userid AND project_name = :project_name"),
                    {"userid": user_id, "project_name": project_name}
                ).fetchone()

                if result_check and result_check[0] > 0:
                    return {
                        "success": False,
                        "error": f"Project name '{project_name}' already exists for this user."
                    }

                db.execute(
                    text("INSERT INTO architecture (userid, architecture_json, project_name) VALUES (:userid, :architecture_json, :project_name)"),
                    {
                        "userid": user_id,
                        "architecture_json": json.dumps(services_json),
                        "project_name": project_name
                    }
                )
                db.commit()

        docs = fetch_documentation_via_llm(query, services_json)

        ec2_docs = docs.get("ec2", "")
        s3_docs = docs.get("s3", "")
        rds_docs = docs.get("rds", "")
        dynamodb_cloudwatch_docs = "\n".join([docs.get("dynamodb", ""), docs.get("cloudwatch", "")])
        apprunner_eks_ecs_docs = "\n".join([docs.get("apprunner", ""), docs.get("eks", ""), docs.get("ecs", "")])
        iam_docs = docs.get("iam", "")
        lambda_docs = docs.get("lambda", "")
        sagemaker_bedrock_docs = "\n".join([docs.get("sagemaker", ""), docs.get("bedrock", "")])
        sns_sqs_docs = "\n".join([docs.get("sns", ""), docs.get("sqs", "")])
        vpc_route53_api_gateway_docs = "\n".join([docs.get("vpc", ""), docs.get("route53", ""), docs.get("apigateway", "")])

        terraform_dir = get_terraform_folder(project_name)
        global TERRAFORM_DIR
        TERRAFORM_DIR = terraform_dir
        os.makedirs(TERRAFORM_DIR, exist_ok=True)

        terraform_code = _generate_terraform_hcl(
            query=query,
            ec2_docs=ec2_docs,
            s3_docs=s3_docs,
            rds_docs=rds_docs,
            dynamodb_cloudwatch_docs=dynamodb_cloudwatch_docs,
            apprunner_eks_ecs_docs=apprunner_eks_ecs_docs,
            iam_docs=iam_docs,
            lambda_docs=lambda_docs,
            sagemaker_bedrock_docs=sagemaker_bedrock_docs,
            sns_sqs_docs=sns_sqs_docs,
            vpc_route53_api_gateway_docs=vpc_route53_api_gateway_docs,
            services_json=services_json
        )

        extract_and_save_terraform(
            terraform_output=terraform_code,
            services=services_json.get("services", []),
            connections=services_json.get("connections", []),
            user_id=user_id,
            project_name=project_name,
            services_json=services_json
        )

        # === Read all Terraform files ===
        tf_files = ["main.tf", "variables.tf", "outputs.tf", "provider.tf"]
        tf_contents = {}
        try:
            for tf_file in tf_files:
                file_path = os.path.join(TERRAFORM_DIR, tf_file)
                if os.path.exists(file_path):
                    with open(file_path, "r") as f:
                        tf_contents[tf_file] = f.read()
                else:
                    tf_contents[tf_file] = ""
        except Exception as e:
            return {"success": False, "error": f"Error reading .tf files: {str(e)}"}

        # === Upload to MinIO ===
        try:
            minio_client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=True
            )
            bucket_name = f"terraform-workspaces-user-{user_id}"
            if not minio_client.bucket_exists(bucket_name):
                minio_client.make_bucket(bucket_name)

            folder_name = os.path.basename(TERRAFORM_DIR.rstrip("/"))
            for root, _, files in os.walk(TERRAFORM_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, TERRAFORM_DIR)
                    object_key = f"{folder_name}/{relative_path}"
                    minio_client.fput_object(bucket_name, object_key, file_path)

        except Exception as e:
            print(f"❌ Error uploading to MinIO: {e}")

        # === Upload to AWS S3 ===
        try:
            s3_config = get_s3_connection_info_with_credentials(user_id)
            s3_bucket = s3_config.get("bucket")
            s3_region = s3_config.get("region")
            s3_prefix = s3_config.get("prefix", "")
            aws_access_key_id = s3_config.get("aws_access_key_id")
            aws_secret_access_key = s3_config.get("aws_secret_access_key")

            if s3_bucket and aws_access_key_id and aws_secret_access_key:
                s3 = boto3.client(
                    's3',
                    region_name=s3_region,
                    aws_access_key_id=aws_access_key_id,
                    aws_secret_access_key=aws_secret_access_key
                )
                folder_name = os.path.basename(TERRAFORM_DIR.rstrip("/"))
                s3_object_prefix = f"{s3_prefix}{folder_name}/" if s3_prefix else f"{folder_name}/"

                for root, _, files in os.walk(TERRAFORM_DIR):
                    for file in files:
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, TERRAFORM_DIR)
                        object_key = f"{s3_object_prefix}{relative_path}"
                        s3.upload_file(file_path, s3_bucket, object_key)

        except Exception as e:
            print(f"❌ Error uploading to AWS S3: {e}")

        # === Cleanup Local Directory ===
        try:
            shutil.rmtree(TERRAFORM_DIR)
        except Exception as e:
            print(f"⚠️ Failed to delete local Terraform directory: {e}")

        # return {
        #     "success": True,
        #     "files": tf_contents,
        #     "message": "Terraform files generated and uploaded successfully."
        # }
        return tf_contents

    except Exception as e:
        return {"success": False, "error": f"Error in generate_terraform_code: {str(e)}"}


# @tool
# def generate_terraform_code(query: str, project_name: str, config: RunnableConfig) -> Dict:
#     """
#     Terraform code generator with DB lookup and storage for architecture diagrams.
#     """
#     user_id = config.get('configurable', {}).get('user_id', 'unknown')
#     if user_id == "unknown":
#         return {"success": False, "error": "User ID missing from configuration"}

#     if not project_name:
#         extracted_project_name = _extract_project_name_from_query(query)
#         print(f"Extracted project name from query: {extracted_project_name}")
#         if extracted_project_name:
#             project_name = extracted_project_name
#             print(f"✅ Extracted project name from query: {project_name}")
#         else:
#             return {
#                 "success": False,
#                 "error": "Project name not provided",
#                 "needs_project_name": True,
#                 "message": "Please provide a project name for your Terraform infrastructure. For example: 'my-webapp' or 'data-pipeline-project'"
#             }

#     print(f"\n🔍 Starting Terraform generation for project: {project_name}")
#     services_json = {}

#     try:
#         with get_db_session() as db:
#             result = db.execute(
#                 text("SELECT architecture_json FROM architecture WHERE userid = :userid AND project_name = :project_name"),
#                 {"userid": user_id, "project_name": project_name}
#             ).fetchone()

#             if result:
#                 print(f"✅ Found existing architecture in DB for user {user_id}, project {project_name}")
#                 services_json = json.loads(result[0]) if isinstance(result[0], str) else result[0]
#             else:
#                 print(f"⚙️ No architecture found. Parsing query...")
#                 services_json = _parse_services_and_connections(query)
#                 services_json["project_name"] = project_name

#                 result_check = db.execute(
#                     text("SELECT COUNT(*) FROM architecture WHERE userid = :userid AND project_name = :project_name"),
#                     {"userid": user_id, "project_name": project_name}
#                 ).fetchone()

#                 if result_check and result_check[0] > 0:
#                     return {
#                         "success": False,
#                         "error": f"Project name '{project_name}' already exists for this user. Please use a different project name."
#                     }

#                 db.execute(
#                     text("INSERT INTO architecture (userid, architecture_json, project_name) VALUES (:userid, :architecture_json, :project_name)"),
#                     {
#                         "userid": user_id,
#                         "architecture_json": json.dumps(services_json),
#                         "project_name": project_name
#                     }
#                 )
#                 db.commit()
#                 print(f"📝 Saved new architecture to DB for user {user_id}, project {project_name}")

#         # === Collect documentation for all relevant services ===
#         docs = fetch_documentation_via_llm(query, services_json)

#         # Extract all supported docs
#         ec2_docs = docs.get("ec2", "")
#         s3_docs = docs.get("s3", "")
#         rds_docs = docs.get("rds", "")
#         dynamodb_cloudwatch_docs = "\n".join([
#             docs.get("dynamodb", ""),
#             docs.get("cloudwatch", "")
#         ])
#         apprunner_eks_ecs_docs = "\n".join([
#             docs.get("apprunner", ""),
#             docs.get("eks", ""),
#             docs.get("ecs", "")
#         ])
#         iam_docs = docs.get("iam", "")
#         lambda_docs = docs.get("lambda", "")
#         sagemaker_bedrock_docs = "\n".join([
#             docs.get("sagemaker", ""),
#             docs.get("bedrock", "")
#         ])
#         sns_sqs_docs = "\n".join([
#             docs.get("sns", ""),
#             docs.get("sqs", "")
#         ])
#         vpc_route53_api_gateway_docs = "\n".join([
#             docs.get("vpc", ""),
#             docs.get("route53", ""),
#             docs.get("apigateway", "")
#         ])

#         # === Create Terraform directory ===
#         terraform_dir = get_terraform_folder(project_name)
#         global TERRAFORM_DIR
#         TERRAFORM_DIR = terraform_dir
#         os.makedirs(TERRAFORM_DIR, exist_ok=True)
#         print(f"📁 Created Terraform directory: {TERRAFORM_DIR}")

#         print("\n🔨 Generating Terraform code...")
#         terraform_code = _generate_terraform_hcl(
#             query=query,
#             ec2_docs=ec2_docs,
#             s3_docs=s3_docs,
#             rds_docs=rds_docs,
#             dynamodb_cloudwatch_docs=dynamodb_cloudwatch_docs,
#             apprunner_eks_ecs_docs=apprunner_eks_ecs_docs,
#             iam_docs=iam_docs,
#             lambda_docs=lambda_docs,
#             sagemaker_bedrock_docs=sagemaker_bedrock_docs,
#             sns_sqs_docs=sns_sqs_docs,
#             vpc_route53_api_gateway_docs=vpc_route53_api_gateway_docs,
#             services_json=services_json
#         )

#         try:
#             extract_and_save_terraform(
#                 terraform_output=terraform_code,
#                 services=services_json.get("services", []),
#                 connections=services_json.get("connections", []),
#                 user_id=user_id,
#                 project_name=project_name,
#                 services_json=services_json
#             )
#             print(f"✅ Saved Terraform file to {TERRAFORM_DIR}/main.tf")
#         except Exception as e:
#             return {"success": False, "error": f"Error saving Terraform file: {str(e)}"}

#         try:
#             with open(os.path.join(TERRAFORM_DIR, "main.tf"), "r") as f:
#                 terraform_content = f.read()
#         except Exception as e:
#             return {"success": False, "error": f"Error reading generated Terraform file: {str(e)}"}

#         # === Upload to MinIO ===
#         try:
#             minio_client = Minio(
#                 MINIO_ENDPOINT,
#                 access_key=MINIO_ACCESS_KEY,
#                 secret_key=MINIO_SECRET_KEY,
#                 secure=True
#             )

#             bucket_name = f"terraform-workspaces-user-{user_id}"
#             if not minio_client.bucket_exists(bucket_name):
#                 minio_client.make_bucket(bucket_name)
#                 print(f"🪣 Created bucket: {bucket_name}")
#             else:
#                 print(f"📦 Bucket exists: {bucket_name}")

#             folder_name = os.path.basename(TERRAFORM_DIR.rstrip("/"))
#             for root, _, files in os.walk(TERRAFORM_DIR):
#                 for file in files:
#                     file_path = os.path.join(root, file)
#                     relative_path = os.path.relpath(file_path, TERRAFORM_DIR)
#                     object_key = f"{folder_name}/{relative_path}"
#                     print(f"⬆️ Uploading: {file_path} -> {object_key}")
#                     minio_client.fput_object(bucket_name, object_key, file_path)
#             print("✅ Terraform directory uploaded to MinIO!")

#         except Exception as e:
#             print(f"❌ Error uploading to MinIO: {e}")
#         # === Upload to S3 (alongside MinIO) ===
#         try:
#             s3_config = get_s3_connection_info_with_credentials(user_id)
#             s3_bucket = s3_config.get("bucket")
#             s3_region = s3_config.get("region")
#             s3_prefix = s3_config.get("prefix", "")
#             aws_access_key_id = s3_config.get("aws_access_key_id")
#             aws_secret_access_key = s3_config.get("aws_secret_access_key")

#             print("S3 Bucket Name:", s3_bucket)

#             if s3_bucket and s3_region and aws_access_key_id and aws_secret_access_key:
#                 s3 = boto3.client(
#                     's3',
#                     region_name=s3_region,
#                     aws_access_key_id=aws_access_key_id,
#                     aws_secret_access_key=aws_secret_access_key
#                 )

#                 folder_name = os.path.basename(TERRAFORM_DIR.rstrip("/"))
#                 s3_object_prefix = f"{s3_prefix}{folder_name}/" if s3_prefix else f"{folder_name}/"

#                 for root, _, files in os.walk(TERRAFORM_DIR):
#                     for file in files:
#                         file_path = os.path.join(root, file)
#                         relative_path = os.path.relpath(file_path, TERRAFORM_DIR)
#                         object_key = f"{s3_object_prefix}{relative_path}"
#                         print(f"⬆️ Uploading to S3: {file_path} -> {object_key}")
#                         s3.upload_file(file_path, s3_bucket, object_key)

#                 print("✅ Terraform directory uploaded to S3!")

#             else:
#                 print("⚠️ Skipping S3 upload - missing S3 configuration or AWS credentials")

#         except Exception as e:
#             print(f"❌ Error uploading to S3: {e}")


#         # === Cleanup local directory ===
#         try:
#             shutil.rmtree(TERRAFORM_DIR)
#             print(f"🧹 Deleted local Terraform directory: {TERRAFORM_DIR}")
#         except Exception as e:
#             print(f"⚠️ Failed to delete local Terraform directory: {e}")

#         return {terraform_content}

#     except Exception as e:
#         error_msg = f"Error in generate_terraform_code: {str(e)}"
#         print(error_msg)
#         return {"success": False, "error": error_msg}



def get_terraform_folder(project_name: str) -> str:
    """Create a numbered terraform folder based on project name"""
    base_folder = f"{project_name}_terraform"
    folder = base_folder
    counter = 1
    
    while os.path.exists(folder):
        folder = f"{project_name}_{counter}_terraform"
        counter += 1
        
    return folder


# def extract_and_save_terraform(terraform_output, services, connections, user_id, project_name, services_json):
#     """Extracts Terraform configurations, validates, fixes errors, and saves the split .tf files."""

#     if not terraform_output:
#         print("❌ Error: No Terraform code generated.")
#         return

#     # Clean raw block if it lacks markdown fencing
#     terraform_output = terraform_output.strip()

#     # Ensure Terraform output directory exists
#     if not os.path.exists(TERRAFORM_DIR):
#         os.makedirs(TERRAFORM_DIR, exist_ok=True)
#         print(f"📁 Created Terraform directory: {TERRAFORM_DIR}")

#     # === Step 1: Validate and Get Final Split Code ===
#     validated_code = validate_terraform_with_openai(terraform_output, services_json)

#     # === Step 2: Extract code blocks by file type ===
#     file_sections = {
#         "main.tf": "",
#         "variables.tf": "",
#         "outputs.tf": "",
#         "provider.tf": ""
#     }

#     matches = re.findall(r"```(.*?)\n(.*?)```", validated_code, re.DOTALL)
#     for tag, code in matches:
#         tag_clean = tag.strip().lower()
#         code = code.strip()

#         if "main.tf" in tag_clean or tag_clean == "main":
#             file_sections["main.tf"] = code
#         elif "variable" in tag_clean or "var.tf" in tag_clean:
#             file_sections["variables.tf"] = code
#         elif "output" in tag_clean or "outputs.tf" in tag_clean:
#             file_sections["outputs.tf"] = code
#         elif "provider" in tag_clean or "provider.tf" in tag_clean:
#             file_sections["provider.tf"] = code
#         elif tag_clean in ["terraform", "hcl"]:
#             # fallback: assume general HCL goes to main.tf if not classified
#             file_sections["main.tf"] += "\n" + code

#     # Fallback if LLM returned no fenced code blocks
#     if all(not content for content in file_sections.values()):
#         file_sections["main.tf"] = validated_code.strip()

#     # === Step 3: Write each file to disk ===
#     for filename, content in file_sections.items():
#         if content:
#             file_path = os.path.join(TERRAFORM_DIR, filename)
#             with open(file_path, "w") as f:
#                 f.write(content)
#             print(f"✅ Saved: {filename}")
#         else:
#             print(f"⚠️ Skipped empty file: {filename}")

#     # === Step 4: Save workspace metadata to DB ===
#     try:
#         with get_db_session() as db:
#             if isinstance(services_json, str):
#                 try:
#                     diagramjson_dict = json.loads(services_json)
#                 except json.JSONDecodeError:
#                     diagramjson_dict = {"error": "Invalid JSON"}
#             else:
#                 diagramjson_dict = services_json

#             new_workspace = WorkspaceCreate(
#                 userid=user_id,
#                 wsname=project_name,
#                 filetype="terraform",
#                 filelocation=TERRAFORM_DIR,  # Use folder instead of a file
#                 diagramjson=diagramjson_dict,
#                 githublocation=""
#             )
#             create_workspace(db=db, workspace=new_workspace)
#             print(f"\n📝 Workspace entry created for: {project_name}")
#     except Exception as e:
#         print(f"❌ Error saving workspace: {e}")

def extract_and_save_terraform(terraform_output, services, connections, user_id, project_name, services_json):
    """Extracts Terraform configurations, validates, fixes errors, and saves the split .tf files."""

    if not terraform_output:
        print("❌ Error: No Terraform code generated.")
        return

    # Clean raw block if it lacks markdown fencing
    terraform_output = terraform_output.strip()

    # Ensure Terraform output directory exists
    if not os.path.exists(TERRAFORM_DIR):
        os.makedirs(TERRAFORM_DIR, exist_ok=True)
        print(f"📁 Created Terraform directory: {TERRAFORM_DIR}")

    # === Step 1: Validate and Get Final Split Code ===
    validated_code = validate_terraform_with_openai(terraform_output, services_json)

    # === Step 2: Extract code blocks by file type ===
    file_sections = {
        "main.tf": "",
        "variables.tf": "",
        "outputs.tf": "",
        "provider.tf": ""
    }

    # Improved regex patterns to match different formats
    # Pattern 1: Look for file-specific headers followed by code blocks
    file_patterns = {
        "provider.tf": [
            r'`provider\.tf`\s*\n```(?:hcl|terraform)?\s*\n(.*?)```',
            r'```provider\.tf\s*\n(.*?)```',
            r'## provider\.tf\s*\n```(?:hcl|terraform)?\s*\n(.*?)```',
            r'# provider\.tf\s*\n```(?:hcl|terraform)?\s*\n(.*?)```'
        ],
        "variables.tf": [
            r'`variables\.tf`\s*\n```(?:hcl|terraform)?\s*\n(.*?)```',
            r'```variables\.tf\s*\n(.*?)```',
            r'## variables\.tf\s*\n```(?:hcl|terraform)?\s*\n(.*?)```',
            r'# variables\.tf\s*\n```(?:hcl|terraform)?\s*\n(.*?)```'
        ],
        "main.tf": [
            r'`main\.tf`\s*\n```(?:hcl|terraform)?\s*\n(.*?)```',
            r'```main\.tf\s*\n(.*?)```',
            r'## main\.tf\s*\n```(?:hcl|terraform)?\s*\n(.*?)```',
            r'# main\.tf\s*\n```(?:hcl|terraform)?\s*\n(.*?)```'
        ],
        "outputs.tf": [
            r'`outputs\.tf`\s*\n```(?:hcl|terraform)?\s*\n(.*?)```',
            r'```outputs\.tf\s*\n(.*?)```',
            r'## outputs\.tf\s*\n```(?:hcl|terraform)?\s*\n(.*?)```',
            r'# outputs\.tf\s*\n```(?:hcl|terraform)?\s*\n(.*?)```'
        ]
    }

    # Try to extract each file using multiple patterns
    for filename, patterns in file_patterns.items():
        for pattern in patterns:
            matches = re.findall(pattern, validated_code, re.DOTALL | re.IGNORECASE)
            if matches:
                file_sections[filename] = matches[0].strip()
                # print(f"✅ Successfully extracted {filename} using pattern: {pattern[:50]}...")
                break
        
        if not file_sections[filename]:
            print(f"⚠️ Could not extract {filename} using any pattern")

    # Fallback: Try the original approach for any remaining files
    if any(not content for content in file_sections.values()):
        print("🔄 Falling back to original regex approach for missing files...")
        
        # Original regex approach
        matches = re.findall(r"```(.*?)\n(.*?)```", validated_code, re.DOTALL)
        for tag, code in matches:
            tag_clean = tag.strip().lower()
            code = code.strip()

            if "main.tf" in tag_clean or tag_clean == "main":
                if not file_sections["main.tf"]:
                    file_sections["main.tf"] = code
                    print("✅ Extracted main.tf via fallback")
            elif "variable" in tag_clean or "var.tf" in tag_clean:
                if not file_sections["variables.tf"]:
                    file_sections["variables.tf"] = code
                    print("✅ Extracted variables.tf via fallback")
            elif "output" in tag_clean or "outputs.tf" in tag_clean:
                if not file_sections["outputs.tf"]:
                    file_sections["outputs.tf"] = code
                    print("✅ Extracted outputs.tf via fallback")
            elif "provider" in tag_clean or "provider.tf" in tag_clean:
                if not file_sections["provider.tf"]:
                    file_sections["provider.tf"] = code
                    print("✅ Extracted provider.tf via fallback")
            elif tag_clean in ["terraform", "hcl"]:
                # fallback: assume general HCL goes to main.tf if not classified
                if not file_sections["main.tf"]:
                    file_sections["main.tf"] += "\n" + code

    # Final fallback: if still no files extracted, put everything in main.tf
    if all(not content for content in file_sections.values()):
        print("🔄 Final fallback: putting all content in main.tf")
        # Remove any markdown formatting
        clean_code = re.sub(r'```[a-zA-Z]*\n?', '', validated_code)
        clean_code = re.sub(r'```', '', clean_code)
        file_sections["main.tf"] = clean_code.strip()

    # Debug: Print what was extracted
    print("\n=== EXTRACTION SUMMARY ===")
    for filename, content in file_sections.items():
        content_preview = content[:100].replace('\n', ' ') if content else "EMPTY"
        print(f"{filename}: {len(content)} chars - {content_preview}...")

    # === Step 3: Write each file to disk ===
    files_written = 0
    for filename, content in file_sections.items():
        if content and content.strip():
            file_path = os.path.join(TERRAFORM_DIR, filename)
            with open(file_path, "w") as f:
                f.write(content)
            print(f"✅ Saved: {filename} ({len(content)} characters)")
            files_written += 1
        else:
            print(f"⚠️ Skipped empty file: {filename}")

    # === Step 5: Save workspace metadata to DB ===
    try:
        with get_db_session() as db:
            if isinstance(services_json, str):
                try:
                    diagramjson_dict = json.loads(services_json)
                except json.JSONDecodeError:
                    diagramjson_dict = {"error": "Invalid JSON"}
            else:
                diagramjson_dict = services_json

            new_workspace = WorkspaceCreate(
                userid=user_id,
                wsname=project_name,
                filetype="terraform",
                filelocation=TERRAFORM_DIR,  # Use folder instead of a file
                diagramjson=diagramjson_dict,
                githublocation=""
            )
            create_workspace(db=db, workspace=new_workspace)
            print(f"\n📝 Workspace entry created for: {project_name}")
    except Exception as e:
        print(f"❌ Error saving workspace: {e}")



def _parse_services_and_connections(query: str) -> Dict[str, Any]:
    """Parse the user query to identify AWS services and their connections."""
    try:
        prompt = """
You are an expert at analyzing infrastructure requirements from text descriptions.

Task: Parse the given user query to identify:
1. Project name (generate a simple one if not specified)
2. AWS services mentioned (EC2, S3, RDS, Lambda, etc.)
3. Connections between these services (which services need to interact)

Return ONLY a valid JSON object with this EXACT structure:
{
  "project_name": "string",
  "services": [
    {
      "id": "timestamp-randomstring",
      "type": "service_type",
      "label": "Service Label",
      "githubRepo": ""
    }
  ],
  "connections": [
    {
      "from_": "service_type1",
      "to": "service_type2"
    }
  ]
}

IMPORTANT RULES:
- Use lowercase service types (ec2, s3, rds, lambda, etc.)
- Generate unique IDs with format: timestamp-randomstring (e.g., "1751377886288-bbhokwtx8")
- Always include "githubRepo": "" (empty string) for each service
- Use proper service labels: "EC2 Instance", "S3 Bucket", "AWS RDS", "Lambda Function", etc.
- Infer logical connections based on typical AWS architecture patterns
- If no connections are obvious, make intelligent assumptions based on services mentioned

Example output format:
{
  "project_name": "web-app-project",
  "services": [
    {
      "id": "1751377886288-bbhokwtx8",
      "type": "ec2",
      "label": "EC2 Instance",
      "githubRepo": ""
    },
    {
      "id": "1751377887375-c7tpua7hc",
      "type": "s3",
      "label": "S3 Bucket",
      "githubRepo": ""
    }
  ],
  "connections": [
    {
      "from_": "ec2",
      "to": "s3"
    }
  ]
}
"""

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"User Query: {query}")
        ]

        llm = ChatOpenAI(model="gpt-4o", temperature=0.1, api_key=OPENAI_API_KEY)
        response = llm.invoke(messages)
        
        # Extract JSON from response
        content = response.content.strip()
        
        # Try to find JSON in the response
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # If no JSON block, try to parse the whole content
            json_str = content
        
        # Clean up any non-JSON text
        json_str = re.sub(r'^[^{]*', '', json_str)
        json_str = re.sub(r'[^}]*$', '', json_str)

        # Parse JSON
        try:
            parsed_json = json.loads(json_str)
            return parsed_json
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
            # Return a default structure
            return {
                "project_name": "default-project",
                "services": [],
                "connections": []
            }
            
    except Exception as e:
        print(f"Error in _parse_services_and_connections: {e}")
        return {
            "project_name": "default-project",
            "services": [],
            "connections": []
        }


# def get_ec2_documentation(query: str) -> str:
#     """Retrieve EC2-related documentation."""
#     try:
#         model = OpenAIEmbeddings(model="text-embedding-3-large", openai_api_key=OPENAI_API_KEY)
#         query_vector = model.embed_query(query)
#         results = list(ec2_collection.aggregate([
#             {
#                 "$vectorSearch": {
#                     "index": "ec2_vector_index",
#                     "queryVector": query_vector,
#                     "path": "embeddings",
#                     "numCandidates": 50,
#                     "limit": 1,
#                     "similarity": "cosine"
#                 }
#             }
#         ]))
#         if results:
#             return results[0].get("combined_text", "No result found.")
#         else:
#             return "No EC2 result found."
        
#     except Exception as e:
#         print(f"Error in get_ec2_documentation: {e}")
#         return f"Error retrieving EC2 documentation: {str(e)}"


# def get_s3_documentation(query: str) -> str:
#     """Retrieve S3-related documentation."""
#     try:
#         model = OpenAIEmbeddings(model="text-embedding-3-large", openai_api_key=OPENAI_API_KEY)
#         query_vector = model.embed_query(query)
#         results = list(s3_collection.aggregate([
#             {
#                 "$vectorSearch": {
#                     "index": "s3_vector_index",
#                     "queryVector": query_vector,
#                     "path": "embeddings",
#                     "numCandidates": 50,
#                     "limit": 1,
#                     "similarity": "cosine"
#                 }
#             }
#         ]))
#         if results:
#             return results[0].get("combined_text", "No result found.")
#         else:
#             return "No S3 result found."
#     except Exception as e:
#         print(f"Error in get_s3_documentation: {e}")
#         return f"Error retrieving S3 documentation: {str(e)}"


# def get_rds_documentation(query: str) -> str:
#     """Retrieve RDS-related documentation."""
#     try:
#         model = OpenAIEmbeddings(model="text-embedding-3-large", openai_api_key=OPENAI_API_KEY)
#         query_vector = model.embed_query(query)
#         results = list(rds_collection.aggregate([
#             {
#                 "$vectorSearch": {
#                     "index": "rds_vector_index",
#                     "queryVector": query_vector,
#                     "path": "embeddings",
#                     "numCandidates": 50,
#                     "limit": 1,
#                     "similarity": "cosine"
#                 }
#             }
#         ]))
#         if results:
#             return results[0].get("combined_text", "No result found.")
#         else:
#             return "No RDS result found."
#     except Exception as e:
#         print(f"Error in get_rds_documentation: {e}")
#         return f"Error retrieving RDS documentation: {str(e)}"


# def _generate_terraform_hcl(query: str, ec2_docs: str = "", s3_docs: str = "", rds_docs: str = "", services_json: dict = None) -> str:
#     """Generate Terraform HCL code based on the query and documentation."""
#     try:
#         # Extract project details from services_json
#         project_name = ""
#         service_details = {}
#         user_connections = []
        
#         if services_json:
#             # Extract project name
#             project_name = services_json.get("project_name", "")
            
#             # Extract service details
#             services = services_json.get("services", [])
#             service_details = {
#                 "services": services,
#                 "total_services": len(services)
#             }
            
#             # Extract connections
#             connections = services_json.get("connections", [])
#             user_connections = connections
            
#             # Debug prints
#             print(f"Project Name: {project_name}")
#             print("\n===== SERVICE DETAILS =====\n")
#             print(json.dumps(service_details, indent=2))
#             print("\n===== USER CONNECTIONS =====\n")
#             print(json.dumps(user_connections, indent=2))
        
#         prompt = """
# You are a Terraform code generator. Use the following rules:
# ONLY output valid HCL Terraform code. Never apologize or mention error handling.
# Avoid all explanatory or fallback language.
# Follow below rules compulsorily:
# - Focus on the **Argument Reference** section for required arguments.
# - Add optional arguments only if they're mentioned or implied in the user query.
# - Strictly ignore the **Example Usage** section. Just use the argument reference and syntax and create terraform file according to user query.
# - From user query understand the requirement of the user which service is need to be connected with other service.And then take care of all the roles and policies and permissions and all the other things.
# - Return only Terraform HCL code, no explanation.
# - Do not use deprecated input parameters strictly.
# - Assume AWS region is 'us-east-1' unless stated otherwise.
# - Generate secure, minimal, and production-ready Terraform code.
# - Always include provider block.
# - IMPORTANT: If services_json is provided, strictly follow the connections specified in it when creating resources.
# - Use meaningful and unique resource names based on the project name provided.
# - Ensure all IAM roles, policies, and security groups are properly configured for the specified connections.
#         """
        
#         # Build context with enhanced project information
#         context = f"User Request: {query}\n\n"
        
#         if project_name:
#             context += f"Project Name: {project_name}\n"
#             context += f"- **Use my project name: `{project_name}`** to generate unique and meaningful names for Terraform resources.\n\n"
        
#         if ec2_docs:
#             context += f"EC2 Documentation:\n{ec2_docs}\n\n"
#         if s3_docs:
#             context += f"S3 Documentation:\n{s3_docs}\n\n"
#         if rds_docs:
#             context += f"RDS Documentation:\n{rds_docs}\n\n"
            
#         if services_json:
#             context += f"Architecture JSON:\n{json.dumps(services_json, indent=2)}\n\n"
#             context += f"Services and Connections JSON:\n{json.dumps(service_details, indent=2)}\n\n"
#             context += f"User Connections:\n{json.dumps(user_connections, indent=2)}\n\n"
#             context += "IMPORTANT: Follow the connections specified in the JSON above when creating resources. Make sure to implement all the necessary IAM roles, policies, and permissions to enable these connections.\n"
#             context += f"Use the project name '{project_name}' as a prefix or suffix for all resource names to ensure uniqueness.\n\n"
        
#         messages = [
#             SystemMessage(content=prompt),
#             HumanMessage(content=context)
#         ]
#         print(f"Messages: {messages}")

#         chat_llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=OPENAI_API_KEY)
#         response = chat_llm.invoke(messages)
#         content = response.content.strip()
        
#         # Extract code from markdown blocks if present
#         if "```" in content:
#             code_blocks = re.findall(r"```(?:hcl|terraform)?\n(.*?)```", content, re.DOTALL)
#             if code_blocks:
#                 return code_blocks[0].strip()
        
#         return content
        
#     except Exception as e:
#         print(f"Error in _generate_terraform_hcl: {e}")
#         return f"# Error generating Terraform code: {str(e)}"


def _generate_terraform_hcl(
    query: str,
    ec2_docs: str = "",
    s3_docs: str = "",
    rds_docs: str = "",
    dynamodb_cloudwatch_docs: str = "",
    apprunner_eks_ecs_docs: str = "",
    iam_docs: str = "",
    lambda_docs: str = "",
    sagemaker_bedrock_docs: str = "",
    sns_sqs_docs: str = "",
    vpc_route53_api_gateway_docs: str = "",
    services_json: dict = None
) -> str:
    """Generate Terraform HCL code based on the query and AWS service documentation."""
    try:
        project_name = ""
        service_details = {}
        user_connections = []

        if services_json:
            project_name = services_json.get("project_name", "")
            services = services_json.get("services", [])
            service_details = {
                "services": services,
                "total_services": len(services)
            }
            user_connections = services_json.get("connections", [])

            print(f"Project Name: {project_name}")
            print("\n===== SERVICE DETAILS =====\n")
            print(json.dumps(service_details, indent=2))
            print("\n===== USER CONNECTIONS =====\n")
            print(json.dumps(user_connections, indent=2))

# 8. **Splitting of Terraform code into files:** 
#                     Split this Terraform configuration into the following separate files according to best practices:

#                     - `provider.tf`: Contains only the `terraform` and `provider` blocks.
#                     - `main.tf`: Contains all resource definitions, data blocks, and modules.
#                     - `variables.tf`: Defines all input variables used across the configuration, including extracted hardcoded values as variables.
#                     - `outputs.tf`: Contains all output definitions relevant to the infrastructure.
        # === Prompt to guide the LLM ===
        prompt = """
                You are an expert-level Terraform Infrastructure as Code (IaC) generator specializing in AWS. Your sole purpose is to produce high-quality, secure, and immediately runnable HCL code.

                **CORE DIRECTIVES (NON-NEGOTIABLE):**
                1.  **HCL Only:** You MUST ONLY output valid HCL Terraform code. Never write explanations, apologies, or conversational text outside of HCL comments.
                2.  **Completeness is Key:** Generate all necessary resources for the request to work. This includes VPCs, subnets, internet gateways, route tables, security groups, and IAM roles/policies. Do not assume any resources exist unless explicitly stated.
                3.  **No Placeholders:** Do not use placeholder values like `"YOUR_VPC_ID"`. Create the resource and reference its attribute directly (e.g., `aws_vpc.main.id`).
                4.  **Argument Reference is Truth:** Your primary source of truth for resource arguments is the **Argument Reference** section of the provided documentation. Required arguments are non-negotiable.
                5.  **Ignore Example Usage:** DO NOT copy-paste from the **Example Usage** sections in the docs. They are often incomplete or use deprecated syntax. Derive your code logic from the Argument Reference.
                6.  **Provider First:** The first block in your code MUST be the `terraform` block, specifying the required AWS provider version (e.g., `~> 5.0`), followed by the `provider "aws"` block with the region.
                7.  **Comment User Variables (CRITICAL):** For any hardcoded values a user might need to change (like instance types, CIDR blocks, or AMI IDs), you MUST add a comment on the same line formatted exactly as: `# TF_VAR :: EDITABLE - USER INPUT REQUIRED`. This is not optional.

                    Maintain full functionality and interdependencies between files. Ensure variable references are used consistently across files where applicable.


                **RESOURCE CONFIGURATION RULES:**
                1.  **Mandatory Tagging:** Every single resource that supports it MUST have a `tags` block. At a minimum, include `Name`, `Project`, and `ManagedBy`. Use the provided `project_name` for the `Project` tag and "Terraform" for the `ManagedBy` tag.
                    - Example: `tags = { Name = "main-vpc", Project = "my-awesome-app", ManagedBy = "Terraform" }`
                2.  **Resource Naming:** Use the `project_name` as a prefix for all resource names to ensure they are unique and identifiable (e.g., `resource "aws_vpc" "my_project_vpc" {}`).
                3.  **User Variables & Comments:** For any values that a user is likely to customize (e.g., `instance_type`, CIDR blocks, specific AMI IDs), add a prominent comment on the same line.
                    - Example: `instance_type = "t3.micro" # USER_VARIABLE: You can change the instance size here.`
                4.  **Outputs:** For critical resources, generate `output` blocks. This is essential for resources like EC2 instance public IPs, RDS endpoint addresses, S3 bucket names, and Load Balancer DNS names.

                **SERVICE-SPECIFIC INSTRUCTIONS:**
                1.  **EC2 Instances:**
                    - **Default AMI:** If the user does not specify an AMI, you MUST use `ami-08a6efd148b1f7504` as the default for the `us-east-1` region. Add a comment indicating this.
                    - **CRITICAL SECURITY GROUP RULE:** When an `aws_instance` is deployed into a VPC (i.e., it has a `subnet_id`), you MUST use `vpc_security_group_ids` to attach security groups. You MUST NOT use the `security_groups` (name-based) argument in this case, as it is for EC2-Classic and will cause an error. Create an `aws_security_group` resource first and then reference its ID.
                2.  **RDS Databases:**
                    - **Subnets:** Always create a new `aws_db_subnet_group` for the RDS instance. Do not attach the database directly to existing subnets.
                    - **Engine Version:** If the user requests an Aurora MySQL database, you MUST use engine version `8.0.mysql_aurora.3.08.1`. For other engines, use a recent, stable version.
                    - **Credentials:** Use hardcoded values as default for password and username.
                    -Ensure the DB subnet group includes subnets from at least two different Availability Zones (e.g., us-east-1a and us-east-1b) when generating Terraform code for AWS RDS.
                3.  **S3 Buckets:**
                    - DO NOT create or reference an `aws_s3_bucket_acl` resource. Avoid using the `acl` argument unless explicitly required.
                    - Use `aws_s3_bucket_policy` for access control instead of ACLs.
                    - Always enable encryption (`server_side_encryption_configuration`) and versioning for the bucket.
                    - Tag all S3 resources properly, as with other AWS resources.
                4. **Lambda Functions:**
                    - **Inline Packaging Only:** Use `archive_file` with inline `source { filename, content }`, output to `"${path.module}/dummy_lambda.zip"`. No `source_dir` or folders.
                    - **Defaults:** Inline Python handler returning HTTP 200; handler `"lambda_function.lambda_handler"` and runtime `"python3.9"` # TF_VAR :: EDITABLE - USER INPUT REQUIRED.
                    - **Wiring:** Set `filename`, `source_code_hash`, and `lifecycle { ignore_changes = [...] }`.
                    - **IAM Role:** Create least-privilege role with `lambda.amazonaws.com` trust.
                    - **Tagging:** Apply standard tags to Lambda and IAM resources.
                5. **ECS (Elastic Container Service):**
                    - **Default Setup:** Fargate launch type, 256 CPU, 512 memory, nginx:latest image # TF_VAR :: EDITABLE - USER INPUT REQUIRED
                    - **Required Resources:** Create `aws_ecs_cluster`, `aws_ecs_task_definition`, `aws_ecs_service`, execution IAM role with `AmazonECSTaskExecutionRolePolicy`, CloudWatch log group (7-day retention)
                    - **Networking:** Security group for container port, public subnets with `assign_public_ip = true`, network mode `"awsvpc"`
                    - **Container Config:** Essential container with awslogs driver, port 80 for web services
                6. **ECS + ECR (Elastic Container Service + Container Registry):**
                    - **Setup:** Create `aws_ecr_repository` with lifecycle policy for future custom images
                    - **Image Strategy:** Use public `nginx:alpine` directly in ECS task definition for reliable deployment # TF_VAR :: EDITABLE - USER INPUT REQUIRED
                    - **Required Resources:** ECR repo (optional for future use), ECS cluster/task/service, IAM role with `AmazonECSTaskExecutionRolePolicy`, CloudWatch logs (7-day)
                    - **Networking:** Security group, public subnets, `assign_public_ip = true`, awsvpc mode, awslogs driver

                **INPUT INTERPRETATION:**
                - **User Query:** This is the primary goal.
                - **Architecture JSON:** This provides the `project_name` for naming/tagging and the `services` and `connections` list. These connections are CRITICAL. Use them to define security group rules, IAM policies, and other dependencies.
                - **Terraform Documentation:** Use the provided docs to find the correct arguments for each resource.
                """
        # prompt = """
        #         You are an expert-level Terraform Infrastructure as Code (IaC) generator specializing in AWS. Your sole purpose is to produce high-quality, secure, and immediately runnable HCL code.

        #         **CRITICAL FILE STRUCTURE REQUIREMENT (MANDATORY):**
        #         You MUST ALWAYS generate EXACTLY 4 separate files with the following structure. This is NON-NEGOTIABLE:

        #         ```
        #         `provider.tf `
        #         [terraform and provider blocks only]

        #         `variables.tf`
        #         [all variable definitions]

        #         `main.tf`
        #         [all resource definitions, data blocks, and modules]

        #         `outputs.tf`
        #         [all output definitions]
        #         ```

        #         **CORE DIRECTIVES (NON-NEGOTIABLE):**
        #         1.  **HCL Only:** You MUST ONLY output valid HCL Terraform code. Never write explanations, apologies, or conversational text outside of HCL comments.
        #         2.  **Four Files Always:** You MUST generate all 4 files (provider.tf, variables.tf, main.tf, outputs.tf) in every response. Never generate just main.tf.
        #         3.  **Completeness is Key:** Generate all necessary resources for the request to work. This includes VPCs, subnets, internet gateways, route tables, security groups, and IAM roles/policies. Do not assume any resources exist unless explicitly stated.
        #         4.  **No Placeholders:** Do not use placeholder values like `"YOUR_VPC_ID"`. Create the resource and reference its attribute directly (e.g., `aws_vpc.main.id`).
        #         5.  **Argument Reference is Truth:** Your primary source of truth for resource arguments is the **Argument Reference** section of the provided documentation. Required arguments are non-negotiable.
        #         6.  **Ignore Example Usage:** DO NOT copy-paste from the **Example Usage** sections in the docs. They are often incomplete or use deprecated syntax. Derive your code logic from the Argument Reference.
        #         7.  **Comment User Variables (CRITICAL):** For any hardcoded values a user might need to change (like instance types, CIDR blocks, or AMI IDs), you MUST add a comment on the same line formatted exactly as: `# TF_VAR :: EDITABLE - USER INPUT REQUIRED`. This is not optional.
        #         8. All required input variables MUST be defined in variables.tf with appropriate type constraints, and MUST include a default value that is either meaningful, securely generated, or derived using the project_name.
        #         **FILE STRUCTURE RULES (STRICT ENFORCEMENT):**

        #         **provider.tf MUST contain:**
        #         - `terraform` block with required_providers and AWS provider version (~> 5.0)
        #         - `provider "aws"` block with region configuration
        #         - Nothing else

        #         **variables.tf MUST contain:**
        #         - ALL input variables used across the configuration
        #         - Default values where appropriate
        #         - Descriptions for each variable
        #         - Type constraints
        #         - Extract ALL hardcoded values as variables with sensible defaults

        #         **main.tf MUST contain:**
        #         - ALL resource definitions (aws_vpc, aws_instance, aws_s3_bucket, etc.)
        #         - ALL data blocks (data sources)
        #         - ALL module calls (if any)
        #         - Use variable references consistently (var.variable_name)
        #         - Nothing else (no providers, variables, or outputs)

        #         **outputs.tf MUST contain:**
        #         - ALL output definitions for critical infrastructure components
        #         - Instance IPs, DNS names, resource IDs, ARNs
        #         - Well-described outputs with meaningful descriptions
        #         - Nothing else

        #         **RESOURCE CONFIGURATION RULES:**
        #         1.  **Mandatory Tagging:** Every single resource that supports it MUST have a `tags` block. At a minimum, include `Name`, `Project`, and `ManagedBy`. Use the provided `project_name` for the `Project` tag and "Terraform" for the `ManagedBy` tag.
        #             - Example: `tags = { Name = "main-vpc", Project = var.project_name, ManagedBy = "Terraform" }`
        #         2.  **Resource Naming:** Use the `project_name` variable as a prefix for all resource names to ensure they are unique and identifiable (e.g., `resource "aws_vpc" "${var.project_name}_vpc" {}`).
        #         3.  **Variable Usage:** ALL hardcoded values must be converted to variables in variables.tf and referenced as var.variable_name in main.tf.
        #         4.  **Comprehensive Outputs:** Generate outputs for ALL critical resources (instance IPs, RDS endpoints, S3 bucket names, Load Balancer DNS names, VPC IDs, subnet IDs, security group IDs).

        #         **SERVICE-SPECIFIC INSTRUCTIONS:**
        #         1.  **EC2 Instances:**
        #             - **Default AMI:** If the user does not specify an AMI, you MUST use `ami-08a6efd148b1f7504` as the default for the `us-east-1` region. Create this as a variable.
        #             - **CRITICAL SECURITY GROUP RULE:** When an `aws_instance` is deployed into a VPC (i.e., it has a `subnet_id`), you MUST use `vpc_security_group_ids` to attach security groups. You MUST NOT use the `security_groups` (name-based) argument in this case, as it is for EC2-Classic and will cause an error. Create an `aws_security_group` resource first and then reference its ID.
        #         2.  **RDS Databases:**
        #             - **Subnets:** Always create a new `aws_db_subnet_group` for the RDS instance. Do not attach the database directly to existing subnets.
        #             - **Engine Version:** If the user requests an Aurora MySQL database, you MUST use engine version `8.0.mysql_aurora.3.08.1`. For other engines, use a recent, stable version.
        #             - **Credentials:** Do not hardcode `username` and `password`. Create variables for these with appropriate descriptions about using secrets management.
        #             - You MUST create at least two subnets in different Availability Zones and use both in the aws_db_subnet_group; do NOT use a single subnet or repeat the same AZ.Do NOT reuse the same AZ for both subnets.Use `availability_zone` argument explicitly for each subnet.
        #         3.  **IAM (CRITICAL):**
        #             - **Least Privilege:** Proactively create all necessary IAM roles (`aws_iam_role`), policies (`aws_iam_policy`), and attachments (`aws_iam_role_policy_attachment`).
        #             - **Specific Policies:** If Service A needs to access Service B (based on the `connections` JSON), create a specific, fine-grained policy for that interaction. Avoid using overly permissive policies like `AdministratorAccess`.

        #         **RESPONSE FORMAT (MANDATORY):**
        #         Your response MUST follow this exact format:

        #         ```
        #         `provider.tf`
        #         [HCL code for terraform and provider blocks]

        #         `variables.tf`
        #         [HCL code for all variable definitions]

        #         `main.tf`
        #         [HCL code for all resources, data blocks, modules]

        #         `outputs.tf`
        #         [HCL code for all output definitions]
        #         ```

        #         **INPUT INTERPRETATION:**
        #         - **User Query:** This is the primary goal.
        #         - **Architecture JSON:** This provides the `project_name` for naming/tagging and the `services` and `connections` list. These connections are CRITICAL. Use them to define security group rules, IAM policies, and other dependencies.
        #         - **Terraform Documentation:** Use the provided docs to find the correct arguments for each resource.

        #         **VALIDATION CHECKLIST:**
        #         Before responding, ensure:
        #         ✓ All 4 files are present (provider.tf, variables.tf, main.tf, outputs.tf)
        #         ✓ No hardcoded values in main.tf (all converted to variables)
        #         ✓ All resources have proper tags using var.project_name
        #         ✓ All critical resources have corresponding outputs
        #         ✓ Provider version is specified as ~> 5.0
        #         ✓ Security groups use vpc_security_group_ids for VPC instances
        #         ✓ All connections from JSON are implemented as IAM policies/security rules
        #         """

        context = f"User Request: {query}\n\n"

        if project_name:
            context += f"Architecture JSON:\n{json.dumps(services_json, indent=2)}\n\n"
            context += (
                "IMPORTANT: Use the connections defined in the JSON to properly link services "
                "(e.g., IAM permissions, networking, security groups, triggers, etc.).\n"
                f"Use the project name '{project_name}' to generate unique and consistent resource names and tags.\n\n"
            )

        # === Append all documentation ===
        if ec2_docs:
            context += f"EC2 Documentation:\n{ec2_docs}\n\n"
        if s3_docs:
            context += f"S3 Documentation:\n{s3_docs}\n\n"
        if rds_docs:
            context += f"RDS Documentation:\n{rds_docs}\n\n"
        if dynamodb_cloudwatch_docs:
            context += f"DynamoDB & CloudWatch Documentation:\n{dynamodb_cloudwatch_docs}\n\n"
        if apprunner_eks_ecs_docs:
            context += f"App Runner / EKS / ECS Documentation:\n{apprunner_eks_ecs_docs}\n\n"
        if iam_docs:
            context += f"IAM Documentation:\n{iam_docs}\n\n"
        if lambda_docs:
            context += f"Lambda Documentation:\n{lambda_docs}\n\n"
        if sagemaker_bedrock_docs:
            context += f"SageMaker / Bedrock Documentation:\n{sagemaker_bedrock_docs}\n\n"
        if sns_sqs_docs:
            context += f"SNS / SQS Documentation:\n{sns_sqs_docs}\n\n"
        if vpc_route53_api_gateway_docs:
            context += f"VPC / Route 53 / API Gateway Documentation:\n{vpc_route53_api_gateway_docs}\n\n"

        # === Append services JSON for guidance ===
        if services_json:
            context += f"Architecture JSON:\n{json.dumps(services_json, indent=2)}\n\n"
            context += f"Services and Connections:\n{json.dumps(service_details, indent=2)}\n\n"
            context += f"User Connections:\n{json.dumps(user_connections, indent=2)}\n\n"
            context += (
                "IMPORTANT: Use these connections to properly link services "
                "(e.g., IAM permissions, networking, security groups, triggers, etc.).\n"
                f"Use '{project_name}' to generate unique and consistent resource names.\n\n"
            )

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=context)
        ]
        print(f"human message: {messages}")
        print(f"🧠 Sending prompt to LLM...")

        chat_llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=OPENAI_API_KEY)
        response = chat_llm.invoke(messages)
        content = response.content.strip()

        # === Extract code block ===
        if "```" in content:
            code_blocks = re.findall(r"```(?:hcl|terraform)?\n(.*?)```", content, re.DOTALL)
            if code_blocks:
                return code_blocks[0].strip()

        return content

    except Exception as e:
        print(f"❌ Error in _generate_terraform_hcl: {e}")
        return f"# Error generating Terraform code: {str(e)}"




# def validate_terraform_with_openai(terraform_code, architecture_json):
#     """
#     Validate and iteratively fix Terraform code using OpenAI to ensure it's runnable.
#     The function will loop up to 5 times and exit early if the code stabilizes.
#     """
#     try:
#         # --- Parse architecture JSON ---
#         if isinstance(architecture_json, str):
#             try:
#                 architecture_json = json.loads(architecture_json)
#             except json.JSONDecodeError:
#                 print("❌ Failed to parse architecture_json.")
#                 return terraform_code

#         services = architecture_json.get("services", [])
#         connections = architecture_json.get("connections", [])

#         services_dict = [s.dict() if hasattr(s, 'dict') else s for s in services]
#         connections_dict = [c.dict() if hasattr(c, 'dict') else c for c in connections]

#         llm = ChatOpenAI(model="gpt-4o", temperature=0.0, api_key=OPENAI_API_KEY)

#         # --- Iterative validation loop ---
#         max_validations = 5
#         current_code = terraform_code

#         for i in range(max_validations):
#             print(f"\n🔁 Validation Loop {i + 1}/{max_validations}")

#             # **CORRECTION 1: Capture the code state at the START of the iteration.**
#             code_at_start_of_iteration = current_code

#             # === STAGE 1: Structural Validation & Fixes ===
#             system_prompt_1 = """
# You are an automated Terraform validation engine. Fix syntax errors, deprecated fields, missing dependencies, and incomplete resources.

# **Rules:**
# 1. Fix all HCL syntax errors.
# 2. Replace deprecated arguments (e.g., use vpc_security_group_ids instead of security_groups if subnet_id is used).
# 3. Add missing AWS dependencies (like subnets, gateways, route tables).
# 4. Always split Terraform into:
#    - provider.tf: provider and terraform blocks
#    - main.tf: resources, modules, data
#    - variables.tf: variable definitions
#    - outputs.tf: output blocks
# 5. Code should pass `terraform plan` without any manual edits.
# 6. Always output each file in a separate fenced markdown block:
#    ```main.tf
# 7. **Default AMI:** If the user does not specify an AMI, you MUST use `ami-08a6efd148b1f7504` as the default for the `us-east-1` region. Add a comment indicating this.

#    ...
# Code snippet

# ...
# etc.

# Return the full set of .tf files using fenced code blocks. No explanations.
# """
#             human_message_1 = f"""
# Architecture to Achieve:

# JSON

# {json.dumps({"services": services_dict, "connections": connections_dict}, indent=2)}
# Terraform Code to Fix:

# Terraform

# {current_code}
# """
#             print("   [Stage 1] Running structural validation...")
#             response_1 = llm.invoke([
#                 SystemMessage(content=system_prompt_1),
#                 HumanMessage(content=human_message_1)
#             ])
#             code_after_stage1 = response_1.content.strip()

#             # === STAGE 2: Connection Validation ===
#             system_prompt_2 = """
# You are a Terraform expert. Validate that all service-to-service connections (IAM roles, security groups, triggers) are properly configured based on the required connections.

# Instructions:

# Use the connections JSON to verify and enforce all links between services.

# DO NOT modify unrelated parts of the configuration.

# Always return split .tf files in fenced blocks like:

# Code snippet

# ...
# Code snippet

# ...
# etc.

# Return only valid HCL blocks. No explanations.
# """
#             human_message_2 = f"""
# Connections to Enforce:

# JSON

# {json.dumps(connections_dict, indent=2)}
# Terraform Code to Check:

# Terraform

# {code_after_stage1}
# """
#             print("   [Stage 2] Running connection validation...")
#             response_2 = llm.invoke([
#                 SystemMessage(content=system_prompt_2),
#                 HumanMessage(content=human_message_2)
#             ])

#             # This is the final, fully processed code for this iteration
#             current_code = response_2.content.strip()

#             # **CORRECTION 2: Perform a single stability check at the END of the iteration.**
#             if current_code == code_at_start_of_iteration:
#                 print(f"✅ Code has stabilized in iteration {i + 1}. Exiting validation loop.")
#                 break
#             else:
#                 print(f"🛠️ Code was refined in iteration {i + 1}. Continuing to next validation cycle.")

#             # If it's the last loop, warn the user.
#             if i == max_validations - 1:
#                 print("⚠️ Validation loop reached maximum iterations. Using the last generated code.")

#         print("\n✅ Validation process complete.")
#         return current_code

#     except Exception as e:
#         print(f"❌ An error occurred in the validation loop: {str(e)}")
#         # Return the last known good code before the error
#         return terraform_code


# def validate_terraform_with_openai(terraform_code, architecture_json):
#     """
#     Enhanced Terraform validation with strict validation rules and error handling.
#     Returns only valid, production-ready Terraform code split into 4 files.
#     """
#     try:
#         # Parse and validate architecture JSON
#         if isinstance(architecture_json, str):
#             try:
#                 architecture_json = json.loads(architecture_json)
#             except json.JSONDecodeError:
#                 print("❌ Failed to parse architecture_json.")
#                 return terraform_code
        
#         # Extract and normalize services/connections
#         services = architecture_json.get("services", [])
#         connections = architecture_json.get("connections", [])
#         project_name = architecture_json.get("project_name", "default-project")
        
#         services_dict = [s.dict() if hasattr(s, 'dict') else s for s in services]
#         connections_dict = [c.dict() if hasattr(c, 'dict') else c for c in connections]
        
#         llm = ChatOpenAI(
#             model="gpt-4o", 
#             temperature=0.0, 
#             api_key=OPENAI_API_KEY,
#             max_tokens=9000 
#         )
        
#         # === Enhanced Validation Prompt ===
#         system_prompt = """
# You are an expert Terraform code validator and fixer specializing in AWS infrastructure.

# **CRITICAL VALIDATION REQUIREMENTS:**
# 1. SYNTAX VALIDATION: Fix ALL HCL syntax errors, missing commas, brackets, quotes
# 2. ARGUMENT VALIDATION: Ensure ALL required arguments are present for each resource
# 3. REFERENCE VALIDATION: Verify all resource references use correct syntax (e.g., aws_vpc.main.id)
# 4. SECURITY VALIDATION: Implement proper security groups, IAM policies based on connections
# 5. DEPENDENCY VALIDATION: Ensure proper resource dependencies and ordering

# **MANDATORY OUTPUT FORMAT:**
# You MUST return EXACTLY 4 files in this format (no deviations allowed):

# `provider.tf`
# [terraform and provider blocks only]

# `variables.tf`
# [all variable definitions with types, descriptions, defaults]

# `main.tf`
# [all resources, data blocks - use variables, no hardcoded values]

# `outputs.tf`
# [all critical outputs with descriptions]

# **VALIDATION RULES (STRICT ENFORCEMENT):**
# 1. NO SYNTAX ERRORS: Every bracket, comma, quote must be correct
# 2. NO PLACEHOLDERS: Replace ALL placeholder values with actual resources/variables
# 3. NO HARDCODED VALUES: Convert all hardcoded values to variables in variables.tf
# 4. PROPER TAGGING: All resources MUST have tags with Name, Project, ManagedBy
# 5. VPC SECURITY GROUPS: Use vpc_security_group_ids (not security_groups) for VPC instances
# 6. COMPLETE RESOURCES: Include ALL required arguments per AWS documentation
# 7. IAM LEAST PRIVILEGE: Create specific IAM policies based on service connections
# 8. PROPER OUTPUTS: Output ALL critical resource attributes (IPs, ARNs, IDs, DNS names)

# **AWS-SPECIFIC FIXES:**
# - EC2 instances in VPC: MUST use vpc_security_group_ids
# - RDS: MUST have db_subnet_group with subnets in different AZs
# - S3: Include versioning, encryption settings
# - IAM: Create roles/policies for service-to-service connections
# - Security Groups: Implement proper ingress/egress rules based on connections
# - Default AMI: ami-08a6efd148b1f7504 for us-east-1

# **CRITICAL ERROR PATTERNS TO FIX:**
# - Missing required arguments (subnet_id, vpc_id, etc.)
# - Incorrect resource references (using names instead of IDs)
# - Missing security groups for EC2 instances
# - Hardcoded values instead of variables
# - Missing IAM permissions for service connections
# - Incomplete resource configurations
# - Missing tags on resources
# - Incorrect provider configuration

# **VALIDATION CHECKLIST (MUST VERIFY ALL):**
# ✓ All 4 files present and properly formatted
# ✓ No HCL syntax errors anywhere
# ✓ All required arguments present for each resource
# ✓ All hardcoded values converted to variables
# ✓ All resources properly tagged
# ✓ Security groups use correct argument names
# ✓ IAM policies implement service connections
# ✓ All critical resources have outputs
# ✓ Provider version specified (~> 5.0)
# ✓ No placeholder values remain

# CRITICAL: If the input code has major structural issues, completely rewrite it following best practices. Do not just patch errors - ensure production-ready code.
# """
        
#         human_prompt = f"""
# **PROJECT:** {project_name}

# **ARCHITECTURE TO IMPLEMENT:**
# ```json
# {json.dumps({"services": services_dict, "connections": connections_dict}, indent=2)}
# ```

# **TERRAFORM CODE TO VALIDATE & FIX:**
# ```hcl
# {terraform_code}
# ```

# **VALIDATION TASK:**
# 1. Fix ALL syntax errors and missing arguments
# 2. Implement ALL service connections from the architecture JSON
# 3. Convert ALL hardcoded values to variables
# 4. Ensure ALL resources have proper tags and outputs
# 5. Return ONLY the 4 Terraform files in the exact format specified

# IMPORTANT: The connections array shows which services need to communicate. Create appropriate IAM policies, security group rules, and networking to enable these connections.
# """
        
#         print("🛠️ Running enhanced Terraform validation...")
        
#         response = llm.invoke([
#             SystemMessage(content=system_prompt),
#             HumanMessage(content=human_prompt)
#         ])
        
#         validated_code = response.content.strip()
#         print("✅ Enhanced validation complete - production-ready code generated")
#         return validated_code
        
#     except Exception as e:
#         print(f"❌ Critical error in validate_terraform_with_openai: {str(e)}")
#         return terraform_code


def validate_terraform_with_openai(terraform_code, architecture_json):
    """
    Enhanced Terraform validation with iterative strict validation (up to 3 passes).
    Returns only valid, production-ready Terraform code split into 4 files.
    """
    
    try:
        # Parse and normalize architecture_json
        if isinstance(architecture_json, str):
            try:
                architecture_json = json.loads(architecture_json)
            except json.JSONDecodeError:
                print("❌ Failed to parse architecture_json.")
                return terraform_code

        services = architecture_json.get("services", [])
        connections = architecture_json.get("connections", [])
        project_name = architecture_json.get("project_name", "default-project")

        services_dict = [s.dict() if hasattr(s, 'dict') else s for s in services]
        connections_dict = [c.dict() if hasattr(c, 'dict') else c for c in connections]

        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.0,
            api_key=OPENAI_API_KEY,  # Make sure this variable is defined
            max_tokens=9000
        )

        # === Prompts ===
        system_prompt = """
You are an expert Terraform code validator and fixer specializing in AWS infrastructure.

**CRITICAL VALIDATION REQUIREMENTS:**
1. SYNTAX VALIDATION: Fix ALL HCL syntax errors, missing commas, brackets, quotes
2. ARGUMENT VALIDATION: Ensure ALL required arguments are present for each resource
3. REFERENCE VALIDATION: Verify all resource references use correct syntax (e.g., aws_vpc.main.id)
4. SECURITY VALIDATION: Implement proper security groups, IAM policies based on connections
5. DEPENDENCY VALIDATION: Ensure proper resource dependencies and ordering
6. COMMENT EDITABLE VALUES: For any hardcoded values a user might need to change (like instance types, CIDR blocks, or AMI IDs), you MUST add a comment on the same line formatted exactly as: `# TF_VAR :: EDITABLE - USER INPUT REQUIRED`. This is not optional. 

**MANDATORY OUTPUT FORMAT:**
You MUST return EXACTLY 4 files in this format (no deviations allowed):

## provider.tf
```hcl
[terraform and provider blocks only]
```

## variables.tf
```hcl
[all variable definitions with types, descriptions, defaults]
```

## main.tf
```hcl
[all resources, data blocks - use variables, no hardcoded values]
```

## outputs.tf
```hcl
[all critical outputs with descriptions]
```

**VALIDATION RULES (STRICT ENFORCEMENT):**
1. NO SYNTAX ERRORS: Every bracket, comma, quote must be correct
2. NO PLACEHOLDERS: Replace ALL placeholder values with actual resources/variables
3. NO HARDCODED VALUES: Convert all hardcoded values to variables in variables.tf
4. PROPER TAGGING: All resources MUST have tags with Name, Project, ManagedBy
5. VPC SECURITY GROUPS: Use vpc_security_group_ids (not security_groups) for VPC instances
6. COMPLETE RESOURCES: Include ALL required arguments per AWS documentation
7. IAM LEAST PRIVILEGE: Create specific IAM policies based on service connections
8. PROPER OUTPUTS: Output ALL critical resource attributes (IPs, ARNs, IDs, DNS names)

**AWS-SPECIFIC FIXES:**
- EC2 instances in VPC: MUST use vpc_security_group_ids
- RDS: MUST have db_subnet_group with subnets in different AZs
- S3: Include versioning, encryption settings
- IAM: Create roles/policies for service-to-service connections
- Security Groups: Implement proper ingress/egress rules based on connections
- Default AMI: ami-08a6efd148b1f7504 for us-east-1

**CRITICAL ERROR PATTERNS TO FIX:**
- Missing required arguments (subnet_id, vpc_id, etc.)
- Incorrect resource references (using names instead of IDs)
- Missing security groups for EC2 instances
- Hardcoded values instead of variables
- Missing IAM permissions for service connections
- Incomplete resource configurations
- Missing tags on resources
- Incorrect provider configuration

**VALIDATION CHECKLIST (MUST VERIFY ALL):**
✓ All 4 files present and properly formatted
✓ No HCL syntax errors anywhere
✓ All required arguments present for each resource
✓ All hardcoded values converted to variables
✓ All resources properly tagged
✓ Security groups use correct argument names
✓ IAM policies implement service connections
✓ All critical resources have outputs
✓ Provider version specified (~> 5.0)
✓ No placeholder values remain

CRITICAL: If the input code has major structural issues, completely rewrite it following best practices. Do not just patch errors - ensure production-ready code.
"""

        base_human_prompt_template = """
**PROJECT:** {project_name}

**ARCHITECTURE TO IMPLEMENT:**
```json
{architecture_json}
```

**TERRAFORM CODE TO VALIDATE & FIX:**
```hcl
{terraform_code}
```

{extra_context}

**VALIDATION TASK:**
1. Fix ALL syntax errors and missing arguments
2. Implement ALL service connections from the architecture JSON
3. Convert ALL hardcoded values to variables
4. Ensure ALL resources have proper tags and outputs
5. Return ONLY the 4 Terraform files in the exact format specified
"""

        # Clean architecture JSON
        architecture_json_cleaned = json.dumps(
            {"services": services_dict, "connections": connections_dict},
            indent=2
        )

        validated_code = terraform_code
        validation_message = ""
        extra_context = ""

        for attempt in range(1, 4):
            print(f"🔁 Iteration {attempt}: Running Terraform validation...")

            # Add error context for retry attempts
            if attempt > 1:
                extra_context = f"""
⚠️ PREVIOUS ITERATION HAD ISSUES: {validation_message}

**STRICT REQUIREMENTS FOR THIS ATTEMPT:**
1. Return EXACTLY 4 files in markdown format with ## headers
2. Each file must contain valid Terraform HCL syntax
3. No syntax errors or missing required arguments
4. All resources properly defined with required parameters

**FORMAT EXAMPLE:**
## provider.tf
```hcl
[valid HCL content]
```

## variables.tf
```hcl
[valid HCL content]
```

## main.tf
```hcl
[valid HCL content]
```

## outputs.tf
```hcl
[valid HCL content]
```
"""

            # Build prompt
            human_prompt = base_human_prompt_template.format(
                project_name=project_name,
                architecture_json=architecture_json_cleaned,
                terraform_code=validated_code,
                extra_context=extra_context
            )

            # Call the model
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])

            validated_code = response.content.strip()

            # Simple check for issues
            if all(file in validated_code for file in ["## provider.tf", "## variables.tf", "## main.tf", "## outputs.tf"]):
                if "syntax error" not in validated_code.lower() and "missing" not in validated_code.lower():
                    print("✅ Validation passed - production-ready Terraform code generated.")
                    break
                else:
                    validation_message = "Syntax or required arguments still missing."
            else:
                validation_message = "Some expected files or headers were not found."

        return validated_code

    except Exception as e:
        print(f"❌ Critical error in validate_terraform_with_openai: {str(e)}")
        return terraform_code



def _extract_project_name_from_query(query: str) -> str:
    """
    Use LLM to intelligently extract project name from the user query.
    
    Args:
        query: The user query about Terraform infrastructure
        
    Returns:
        str: The extracted project name or None if not found
    """
    try:
        prompt = """
You are an AI assistant that extracts project names from user queries about Terraform infrastructure.

INSTRUCTIONS:
1. Analyze the user query and identify if it contains a project name
2. Look for phrases like "project name is X", "for project X", "named X", etc.
3. If you find a project name, return ONLY the project name as a single word or hyphenated phrase
4. If no project name is mentioned, return "None"

IMPORTANT:
- Return ONLY the project name or "None" - no other text
- Project names should be alphanumeric with optional hyphens or underscores
- Do not include quotes or other punctuation in the project name
- Do not explain your reasoning

EXAMPLES:
Query: "Generate terraform code for an EC2 instance for project my-webapp"
Response: my-webapp

Query: "Create S3 bucket with the project name test_project"
Response: test_project

Query: "I need terraform for a lambda function"
Response: None
"""

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=query)
        ]

        llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=OPENAI_API_KEY)
        response = llm.invoke(messages)
        
        # Extract the project name from the response
        project_name = response.content.strip()
        
        # Return None if the LLM couldn't find a project name
        if project_name.lower() == "none":
            return None
            
        return project_name
        
    except Exception as e:
        print(f"Error extracting project name with LLM: {e}")
        return None

# def fetch_documentation_via_llm(query: str, services_json: dict) -> Dict[str, str]:
#     """
#     Uses LLM to analyze the user query and services_json to:
#     1. Generate keyword-like subqueries for each service type.
#     2. Decide which MongoDB fetch functions to call.
#     3. Collect and return service documentation.

#     Returns:
#         dict: Dictionary with service type as keys (ec2, s3, rds) and documentation as values.
#     """
#     try:
#         prompt = """
# You are an expert AI assistant that:
# 1. Analyzes the user query and architecture_json (services + connections)
# 2. Determines which AWS services (ec2, s3, rds) are required
# 3. For each service, generate a keyword-focused query to pass to a MongoDB vector search
# 4. Return a JSON with structure:
# {
#   "ec2": "subquery for ec2",
#   "s3": "subquery for s3",
#   "rds": "subquery for rds"
# }
# If a service is not needed, set its value to null.
# IMPORTANT: Only return JSON, no explanation.
#         """

#         messages = [
#             SystemMessage(content=prompt),
#             HumanMessage(content=f"User Query: {query}\n\nArchitecture JSON:\n{json.dumps(services_json, indent=2)}")
#         ]

#         llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=OPENAI_API_KEY)
#         response = llm.invoke(messages)

#         # Extract and parse JSON from the response
#         json_str = re.sub(r'^.*?\{', '{', response.content.strip(), flags=re.DOTALL)
#         json_str = re.sub(r'\}.*$', '}', json_str, flags=re.DOTALL)
#         subquery_map = json.loads(json_str)

#         documentation = {
#             "ec2": "",
#             "s3": "",
#             "rds": ""
#         }

#         if subquery_map.get("ec2"):
#             documentation["ec2"] = get_ec2_documentation(subquery_map["ec2"])
#             print(f"EC2 Docs: {documentation['ec2']}")
#             print(f"EC2 Subquery: {subquery_map['ec2']}")
#         if subquery_map.get("s3"):
#             documentation["s3"] = get_s3_documentation(subquery_map["s3"])
#             print(f"S3 Docs: {documentation['s3']}")
#             print(f"S3 Subquery: {subquery_map['s3']}")
#         if subquery_map.get("rds"):
#             documentation["rds"] = get_rds_documentation(subquery_map["rds"])
#             print(f"RDS Docs: {documentation['rds']}")
#             print(f"RDS Subquery: {subquery_map['rds']}")   
#         return documentation

#     except Exception as e:
#         print(f"Error in fetch_documentation_via_llm: {e}")
#         return {
#             "ec2": "",
#             "s3": "",
#             "rds": ""
#         }

def fetch_documentation_via_llm(query: str, services_json: dict) -> Dict[str, str]:
    """
    Uses LLM to analyze the user query and architecture_json and:
    1. Determines which AWS services are required.
    2. Generates keyword-style subqueries.
    3. Calls vector search tools with resource-specific subqueries.
    Returns:
        Dict[str, str]: Mapping of service to documentation text.
    """
    try:
        prompt = """
You are an expert AI assistant that:
1. Analyzes the user query and architecture JSON.
2. Identifies which AWS services are needed from this list:
   ec2, s3, rds, dynamodb, cloudwatch, apprunner, eks, ecs, iam, lambda, sagemaker, bedrock, sns, sqs, vpc, route53, apigateway
3. For each needed service, generate a short subquery for MongoDB vector search.
4. Return a JSON like:
{
  "ec2": "subquery for ec2",
  "s3": "subquery for s3",
  ...
}
Only include a key if the service is needed. If not needed, exclude it.
Only return valid JSON. No explanation.
        """

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"User Query: {query}\n\nArchitecture JSON:\n{json.dumps(services_json, indent=2)}")
        ]

        llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=OPENAI_API_KEY)
        response = llm.invoke(messages)

        # Clean and extract JSON
        json_str = re.sub(r'^.*?\{', '{', response.content.strip(), flags=re.DOTALL)
        json_str = re.sub(r'\}.*$', '}', json_str, flags=re.DOTALL)
        subquery_map = json.loads(json_str)

        docs = {}

        # === Basic Tools ===
        if "ec2" in subquery_map:
            docs["ec2"] = get_ec2_documentation(subquery_map["ec2"])
        if "s3" in subquery_map:
            docs["s3"] = get_s3_documentation(subquery_map["s3"])
        if "rds" in subquery_map:
            docs["rds"] = get_rds_documentation(subquery_map["rds"])
        if "iam" in subquery_map:
            docs["iam"] = get_iam_documentation(subquery_map["iam"])
        if "lambda" in subquery_map:
            docs["lambda"] = get_lambda_documentation(subquery_map["lambda"])

        for service in ["dynamodb", "cloudwatch"]:
            if service in subquery_map:
                docs[service] = get_dynamodb_documentation(subquery_map[service])

        # === Composite: apprunner, eks, ecs ===
        for service in ["apprunner", "eks", "ecs"]:
            if service in subquery_map:
                docs[service] = get_apprunner_documentation(subquery_map[service])

        # === Composite: sagemaker + bedrock ===
        for service in ["sagemaker", "bedrock"]:
            if service in subquery_map:
                docs[service] = get_sagemaker_documentation(subquery_map[service])

        # === Composite: sns + sqs ===
        for service in ["sns", "sqs"]:
            if service in subquery_map:
                docs[service] = get_sns_sqs_documentation(subquery_map[service])

        # === Composite: vpc + route53 + apigateway ===
        for service in ["vpc", "route53", "apigateway"]:
            if service in subquery_map:
                docs[service] = get_vpc_documentation(subquery_map[service])

        return docs

    except Exception as e:
        print(f"❌ Error in fetch_documentation_via_llm: {e}")
        return {}


def get_ec2_documentation(query): return fetch_doc(ec2_collection, "ec2_vector_index", query)
def get_s3_documentation(query): return fetch_doc(s3_collection, "s3_vector_index", query)
def get_rds_documentation(query): return fetch_doc(rds_collection, "rds_vector_index", query)
def get_dynamodb_documentation(query): return fetch_doc(dynamodb_collection, "dynamodb_cloudwatch_vector_index", query)
def get_apprunner_documentation(query): return fetch_doc(apprunner_collection, "apprunner_eks_ecs_vector_index", query)
def get_iam_documentation(query): return fetch_doc(iam_collection, "iam_vector_index", query)
def get_lambda_documentation(query): return fetch_doc(lambda_collection, "lambda_vector_index", query)
def get_sagemaker_documentation(query): return fetch_doc(sagemaker_collection, "sagemaker_bedrock_vector_index", query)
def get_sns_sqs_documentation(query): return fetch_doc(sns_sqs_collection, "sns_sqs_vector_index", query)
def get_vpc_documentation(query): return fetch_doc(vpc_collection, "vpc_route53_api_gateway_vector_index", query)