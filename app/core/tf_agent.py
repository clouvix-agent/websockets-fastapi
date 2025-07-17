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
You are a Terraform code generator. Use the following rules:
ONLY output valid HCL Terraform code. Never apologize or mention error handling.
Avoid all explanatory or fallback language.
Follow below rules compulsorily:
- Focus on the **Argument Reference** section for required arguments.
- Add optional arguments only if they're mentioned or implied in the user query.
- Strictly ignore the **Example Usage** section.
- From user query and docs, understand the requirement of the user and service interconnections.
- Take care of roles, policies, networking, IAM, security groups, etc.
- Return only Terraform HCL code, no explanation.
- Do not use deprecated input parameters strictly.
- Assume AWS region is 'us-east-1' unless otherwise stated.
- Always include provider block.
- For RDS database terraform code always take engine version as "8.0.mysql_aurora.3.08.1" .
- For RDS Database terraform code always first creates subnets and then uses that subnets in the RDS database resource.
- Follow the connections in services_json.
- Use unique resource names derived from the project name.
- While creating the terraform code for any resource checks its stable recent versions. Like for database resource check its latest version and use it.
- Ensure all required IAM roles, policies, and connectivity resources are included.
        """

        context = f"User Request: {query}\n\n"

        if project_name:
            context += f"Project Name: {project_name}\n"
            context += f"- Use the project name `{project_name}` for naming resources.\n\n"

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



def validate_terraform_with_openai(terraform_code, architecture_json):
    """Validate and fix Terraform code using OpenAI."""
    try:
        # Ensure architecture_json is a dictionary
        if isinstance(architecture_json, str):
            try:
                architecture_json = json.loads(architecture_json)
            except json.JSONDecodeError:
                print("Error parsing architecture_json as JSON string")
                return terraform_code
                
        services = architecture_json.get("services", [])
        connections = architecture_json.get("connections", [])

        # Convert services and connections to dict if they're not already
        services_dict = []
        for service in services:
            if hasattr(service, 'dict'):
                services_dict.append(service.dict())
            elif isinstance(service, dict):
                services_dict.append(service)
            else:
                services_dict.append(str(service))

        connections_dict = []
        for conn in connections:
            if hasattr(conn, 'dict'):
                connections_dict.append(conn.dict())
            elif isinstance(conn, dict):
                connections_dict.append(conn)
            else:
                connections_dict.append(str(conn))

        llm = ChatOpenAI(model="gpt-4o", temperature=0.1, api_key=OPENAI_API_KEY)

        messages = [
            SystemMessage(content="You are a senior DevOps engineer specializing in Terraform. Validate the configuration for production-ready deployment, checking syntax, dependencies, security, and best practices. Confirm it can execute `terraform apply` successfully without errors or additional manual steps.."),
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
            Check if user run terraform apply then it should able to apply in one go . So validate the terraform code in deep and make sure it is correct and complete.
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
            """)
        ]

        response = llm.invoke(messages)
        validated_code = re.sub(r"```hcl|```", "", response.content.strip()).strip()

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
            {validated_code}
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
        final_code = re.sub(r"```hcl|```", "", response.content.strip()).strip()

        return final_code

    except Exception as e:
        print(f"Error in validate_terraform_with_openai: {e}")
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