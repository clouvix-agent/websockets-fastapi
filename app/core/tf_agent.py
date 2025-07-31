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

@tool
def generate_terraform_code(query: str, project_name: str, config: RunnableConfig) -> Dict:
    """
    Terraform code generator with DB lookup and storage for architecture diagrams.
    """
    user_id = config.get('configurable', {}).get('user_id', 'unknown')
    if user_id == "unknown":
        return {"success": False, "error": "User ID missing from configuration"}

    if not project_name:
        extracted_project_name = _extract_project_name_from_query(query)
        print(f"Extracted project name from query: {extracted_project_name}")
        if extracted_project_name:
            project_name = extracted_project_name
            print(f"✅ Extracted project name from query: {project_name}")
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
                print(f"✅ Found existing architecture in DB for user {user_id}, project {project_name}")
                services_json = json.loads(result[0]) if isinstance(result[0], str) else result[0]
            else:
                print(f"⚙️ No architecture found. Parsing query...")
                services_json = _parse_services_and_connections(query)
                services_json["project_name"] = project_name

                result_check = db.execute(
                    text("SELECT COUNT(*) FROM architecture WHERE userid = :userid AND project_name = :project_name"),
                    {"userid": user_id, "project_name": project_name}
                ).fetchone()

                if result_check and result_check[0] > 0:
                    return {
                        "success": False,
                        "error": f"Project name '{project_name}' already exists for this user. Please use a different project name."
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
                print(f"📝 Saved new architecture to DB for user {user_id}, project {project_name}")

        # === Collect documentation for all relevant services ===
        docs = fetch_documentation_via_llm(query, services_json)

        # Extract all supported docs
        ec2_docs = docs.get("ec2", "")
        s3_docs = docs.get("s3", "")
        rds_docs = docs.get("rds", "")
        dynamodb_cloudwatch_docs = "\n".join([
            docs.get("dynamodb", ""),
            docs.get("cloudwatch", "")
        ])
        apprunner_eks_ecs_docs = "\n".join([
            docs.get("apprunner", ""),
            docs.get("eks", ""),
            docs.get("ecs", "")
        ])
        iam_docs = docs.get("iam", "")
        lambda_docs = docs.get("lambda", "")
        sagemaker_bedrock_docs = "\n".join([
            docs.get("sagemaker", ""),
            docs.get("bedrock", "")
        ])
        sns_sqs_docs = "\n".join([
            docs.get("sns", ""),
            docs.get("sqs", "")
        ])
        vpc_route53_api_gateway_docs = "\n".join([
            docs.get("vpc", ""),
            docs.get("route53", ""),
            docs.get("apigateway", "")
        ])

        # === Create Terraform directory ===
        terraform_dir = get_terraform_folder(project_name)
        global TERRAFORM_DIR
        TERRAFORM_DIR = terraform_dir
        os.makedirs(TERRAFORM_DIR, exist_ok=True)
        print(f"📁 Created Terraform directory: {TERRAFORM_DIR}")

        print("\n🔨 Generating Terraform code...")
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

        try:
            extract_and_save_terraform(
                terraform_output=terraform_code,
                services=services_json.get("services", []),
                connections=services_json.get("connections", []),
                user_id=user_id,
                project_name=project_name,
                services_json=services_json
            )
            print(f"✅ Saved Terraform file to {TERRAFORM_DIR}/main.tf")
        except Exception as e:
            return {"success": False, "error": f"Error saving Terraform file: {str(e)}"}

        try:
            with open(os.path.join(TERRAFORM_DIR, "main.tf"), "r") as f:
                terraform_content = f.read()
        except Exception as e:
            return {"success": False, "error": f"Error reading generated Terraform file: {str(e)}"}

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
                print(f"🪣 Created bucket: {bucket_name}")
            else:
                print(f"📦 Bucket exists: {bucket_name}")

            folder_name = os.path.basename(TERRAFORM_DIR.rstrip("/"))
            for root, _, files in os.walk(TERRAFORM_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, TERRAFORM_DIR)
                    object_key = f"{folder_name}/{relative_path}"
                    print(f"⬆️ Uploading: {file_path} -> {object_key}")
                    minio_client.fput_object(bucket_name, object_key, file_path)
            print("✅ Terraform directory uploaded to MinIO!")

        except Exception as e:
            print(f"❌ Error uploading to MinIO: {e}")
        # === Upload to S3 (alongside MinIO) ===
        try:
            s3_config = get_s3_connection_info_with_credentials(user_id)
            s3_bucket = s3_config.get("bucket")
            s3_region = s3_config.get("region")
            s3_prefix = s3_config.get("prefix", "")
            aws_access_key_id = s3_config.get("aws_access_key_id")
            aws_secret_access_key = s3_config.get("aws_secret_access_key")

            print("S3 Bucket Name:", s3_bucket)

            if s3_bucket and s3_region and aws_access_key_id and aws_secret_access_key:
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
                        print(f"⬆️ Uploading to S3: {file_path} -> {object_key}")
                        s3.upload_file(file_path, s3_bucket, object_key)

                print("✅ Terraform directory uploaded to S3!")

            else:
                print("⚠️ Skipping S3 upload - missing S3 configuration or AWS credentials")

        except Exception as e:
            print(f"❌ Error uploading to S3: {e}")


        # === Cleanup local directory ===
        try:
            shutil.rmtree(TERRAFORM_DIR)
            print(f"🧹 Deleted local Terraform directory: {TERRAFORM_DIR}")
        except Exception as e:
            print(f"⚠️ Failed to delete local Terraform directory: {e}")

        return {terraform_content}

    except Exception as e:
        error_msg = f"Error in generate_terraform_code: {str(e)}"
        print(error_msg)
        return {"success": False, "error": error_msg}



def get_terraform_folder(project_name: str) -> str:
    """Create a numbered terraform folder based on project name"""
    base_folder = f"{project_name}_terraform"
    folder = base_folder
    counter = 1
    
    while os.path.exists(folder):
        folder = f"{project_name}_{counter}_terraform"
        counter += 1
        
    return folder


def extract_and_save_terraform(terraform_output, services, connections, user_id, project_name, services_json):
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
    validated_code = validate_terraform_with_openai(terraform_output, services_json)

    # Save the final validated Terraform file
    final_tf_path = os.path.join(TERRAFORM_DIR, "main.tf")
    with open(final_tf_path, "w") as tf_file:
        tf_file.write(validated_code)

    # Add an entry to workspace table
    try:
        with get_db_session() as db:
            # Ensure services_json is a dictionary for the WorkspaceCreate model
            if isinstance(services_json, str):
                try:
                    diagramjson_dict = json.loads(services_json)
                except json.JSONDecodeError:
                    print("Error parsing services_json as JSON string")
                    diagramjson_dict = {"error": "Failed to parse JSON"}
            else:
                # If it's already a dict, use it directly
                diagramjson_dict = services_json
            
            new_workspace = WorkspaceCreate(
                userid=user_id,
                wsname=project_name,
                filetype="terraform",
                filelocation=final_tf_path,
                diagramjson=diagramjson_dict,
                githublocation=""
            )
            create_workspace(db=db, workspace=new_workspace)
            print(f"\n✅ Final validated Terraform file saved at: {final_tf_path}")
    except Exception as e:
        print(f"Error saving to workspace: {e}")


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
                    - **Credentials:** Do not hardcode `username` and `password`. Use a comment to instruct the user to use a secrets management solution. Example: `# IMPORTANT: Do not hardcode credentials. Use Terraform variables or a secrets manager.`
                3.  **IAM (CRITICAL):**
                    - **Least Privilege:** Proactively create all necessary IAM roles (`aws_iam_role`), policies (`aws_iam_policy`), and attachments (`aws_iam_role_policy_attachment`).
                    - **Specific Policies:** If Service A needs to access Service B (based on the `connections` JSON), create a specific, fine-grained policy for that interaction. Avoid using overly permissive policies like `AdministratorAccess`.

                **INPUT INTERPRETATION:**
                - **User Query:** This is the primary goal.
                - **Architecture JSON:** This provides the `project_name` for naming/tagging and the `services` and `connections` list. These connections are CRITICAL. Use them to define security group rules, IAM policies, and other dependencies.
                - **Terraform Documentation:** Use the provided docs to find the correct arguments for each resource.
                """

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
#     """ Validate and iteratively fix Terraform code using OpenAI to ensure it's runnable.
#     The function will loop 3 times to progressively refine the code."""
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
#         max_validations = 3
#         current_code = terraform_code
#         for i in range(max_validations):
#             print(f"🔎 Starting Validation Loop: Iteration {i + 1}/{max_validations}")
#         messages = [
#             SystemMessage(content="You are a senior DevOps engineer specializing in Terraform. Validate the configuration for production-ready deployment, checking syntax, dependencies, security, and best practices. Confirm it can execute `terraform apply` successfully without errors or additional manual steps.."),
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
#             Check if user run terraform apply then it should able to apply in one go . So validate the terraform code in deep and make sure it is correct and complete.
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


def validate_terraform_with_openai(terraform_code, architecture_json):
    """
    Validate and iteratively fix Terraform code using OpenAI to ensure it's runnable.
    The function will loop 3 times to progressively refine the code.
    """
    try:
        # --- Data Preparation (Restored from your original code) ---
        if isinstance(architecture_json, str):
            try:
                architecture_json = json.loads(architecture_json)
            except json.JSONDecodeError:
                print("Error parsing architecture_json as JSON string")
                return terraform_code
        
        services = architecture_json.get("services", [])
        connections = architecture_json.get("connections", [])

        # Convert services to a dictionary list
        services_dict = []
        for service in services:
            if hasattr(service, 'dict'):
                services_dict.append(service.dict())
            elif isinstance(service, dict):
                services_dict.append(service)
            else:
                services_dict.append(str(service))

        # Convert connections to a dictionary list
        connections_dict = []
        for conn in connections:
            if hasattr(conn, 'dict'):
                connections_dict.append(conn.dict())
            elif isinstance(conn, dict):
                connections_dict.append(conn)
            else:
                connections_dict.append(str(conn))

        llm = ChatOpenAI(model="gpt-4o", temperature=0.0, api_key=OPENAI_API_KEY)
        
        # --- New Iterative Validation Loop ---
        max_validations = 3
        current_code = terraform_code
        
        for i in range(max_validations):
            print(f"🔎 Starting Validation Loop: Iteration {i + 1}/{max_validations}")

            # === STAGE 1: Deep Validation and Correction Prompt ===
            system_prompt_1 = """
You are an automated Terraform validation and correction engine. Your single purpose is to meticulously analyze, correct, and finalize a given Terraform configuration to guarantee it passes `terraform apply` on the first attempt without any errors.

**YOUR CORRECTION CHECKLIST (NON-NEGOTIABLE):**
1.  **Fix All Syntax Errors:** Correct any and all HCL syntax violations, including missing brackets, incorrect operators, or invalid expressions.
2.  **Replace Deprecated Arguments:** Identify and replace any deprecated resource arguments or attributes with their modern equivalents. For example, if you see `security_groups` used with a `subnet_id` on an `aws_instance`, you MUST replace it with `vpc_security_group_ids`.
3.  **Resolve Logical Errors & Dependencies:** Add missing `depends_on` attributes where implicit dependency is not enough. Correct invalid resource references. Ensure the order of resources is logical for creation.
4.  **Ensure Completeness:** Add any missing mandatory resources required for the configuration to be functional (e.g., an `aws_internet_gateway` and `aws_route_table` for a public EC2 instance).
5.  **Adhere to Best Practices:** Ensure the code follows modern security and AWS best practices, including the principle of least privilege for IAM policies.

**RESPONSE FORMAT:**
- If the code is already perfect, return it unchanged.
- If you make corrections, return the ENTIRE, complete, corrected Terraform HCL code.
- DO NOT include explanations, apologies, or any text outside of the HCL code.
"""
            
            human_message_1 = f"""
            **Architecture to Achieve:**
            ```json
            {json.dumps({"services": services_dict, "connections": connections_dict}, indent=2)}
            ```

            **Terraform Code to Validate and Fix:**
            ```hcl
            {current_code}
            ```
            Please perform a strict validation and correction on the code above based on all your rules. The final output must be perfect and ready for an immediate `terraform apply`.
            """
            
            messages_1 = [
                SystemMessage(content=system_prompt_1),
                HumanMessage(content=human_message_1)
            ]

            response_1 = llm.invoke(messages_1)
            validated_code = re.sub(r"```hcl|```", "", response_1.content.strip()).strip()
            print(f"  [Iteration {i + 1}] Stage 1 (Correction) Complete.")

            # === STAGE 2: Connection Integrity Check ===
            system_prompt_2 = """
You are an expert Terraform connection validator. Your task is to ensure a Terraform file correctly implements all required service-to-service connections as defined in a JSON object.

**VALIDATION RULES:**
1.  **Check Connections:** Review the `connections` JSON and verify that each link is correctly implemented in the Terraform code (e.g., via security group rules, IAM policies, subnet associations, etc.).
2.  **Add Missing Connections Only:** If a connection is missing, add the necessary, syntactically correct resource or attribute to fix it.
3.  **Do Not Modify Other Code:** Do not remove or change any other part of the configuration that is not directly related to fixing a missing connection.
4.  If all connections are present, return the file as is.

**RESPONSE FORMAT:**
- Return ONLY the complete, valid Terraform HCL file. No explanations.
"""
            human_message_2 = f"""
            **Required Connections:**
            ```json
            {json.dumps(connections_dict, indent=2)}
            ```

            **Current Terraform Configuration:**
            ```hcl
            {validated_code}
            ```
            Please validate that all required service connections are implemented. Add any missing connection logic and return the complete file.
            """
            
            messages_2 = [
                SystemMessage(content=system_prompt_2),
                HumanMessage(content=human_message_2)
            ]

            response_2 = llm.invoke(messages_2)
            final_code_for_iteration = re.sub(r"```hcl|```", "", response_2.content.strip()).strip()
            
            # Prepare for the next loop by updating the code to be validated.
            current_code = final_code_for_iteration
            print(f"  [Iteration {i + 1}] Stage 2 (Connections) Complete.")

        # After the loop, `current_code` holds the final, thrice-validated code.
        print("✅ Validation process complete.")
        return current_code

    except Exception as e:
        print(f"❌ Error during the validation loop: {e}")
        return terraform_code  # Return original code if validation fails

# def _create_services_summary(services_json: dict) -> str:
#     """Create a human-readable summary of the services and connections."""
#     try:
#         summary = []
        
#         # Project name
#         project_name = services_json.get("project_name", "Unnamed Project")
#         summary.append(f"🔶 Project: {project_name}")
        
#         # Services
#         services = services_json.get("services", [])
#         if services:
#             summary.append("\n🔷 Services:")
#             for service in services:
#                 label = service.get('label', 'Unknown')
#                 service_type = service.get('type', 'unknown')
#                 summary.append(f"  • {label} ({service_type})")
#         else:
#             summary.append("\n🔷 Services: None identified")
        
#         # Connections
#         connections = services_json.get("connections", [])
#         summary.append("\n🔗 Connections:")
#         if connections:
#             for conn in connections:
#                 from_service = conn.get('from_', 'unknown')
#                 to_service = conn.get('to', 'unknown')
#                 summary.append(f"  • {from_service} → {to_service}")
#         else:
#             summary.append("  • No connections defined")
        
#         return "\n".join(summary)
        
#     except Exception as e:
#         return f"Error creating summary: {str(e)}"


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