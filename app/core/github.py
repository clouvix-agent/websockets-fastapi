# import os
# import shutil
# import json
# import tempfile
# import time
# import errno
# import stat
# from github import Github
# from git import Repo
# from langchain_core.runnables import RunnableConfig
# from app.db.connection import get_user_connections_by_type
# from app.database import get_db
# from sqlalchemy.orm import Session
# from langchain.tools import tool
# from minio import Minio
# from minio.error import S3Error

# @tool
# def create_pr(github_url: str, project_name: str, config: RunnableConfig) -> str:
#     """
#     Creates a pull request in the provided GitHub repository with .tf files
#     from the MinIO bucket for the specified project name.
#     """
#     print("Creating pull request with .tf files...")
#     user_id = config['configurable'].get('user_id', 'unknown')

#     # Input validation
#     if not github_url:
#         return "Error: GitHub repository URL is required."
#     if not project_name:
#         return "Error: Project name is required."
#     if not user_id:
#         return "Error: User ID is required."

#     # Use a unique temporary directory for temp_repo to avoid conflicts
#     TEMP_DIR = os.path.join(tempfile.gettempdir(), f"temp_repo_{int(time.time())}")
#     temp_dir = tempfile.mkdtemp()
#     download_path = os.path.join(temp_dir, f"{project_name}_terraform")
#     os.makedirs(download_path, exist_ok=True)

#     def force_remove_readonly(func, path, excinfo):
#         """Handle read-only files by changing permissions and retrying deletion."""
#         os.chmod(path, stat.S_IWRITE)
#         func(path)

#     def robust_rmtree(directory, retries=5, delay=1):
#         """Attempt to remove a directory with retries, handling permission issues and locks."""
#         if not os.path.exists(directory):
#             print(f"🧹 Directory {directory} does not exist, no cleanup needed.")
#             return
#         for attempt in range(retries):
#             try:
#                 shutil.rmtree(directory, onerror=force_remove_readonly)
#                 print(f"🧹 Successfully deleted directory: {directory}")
#                 return
#             except PermissionError as e:
#                 print(f"Permission error deleting {directory}: {e}. Retrying ({attempt + 1}/{retries})...")
#                 time.sleep(delay)
#             except OSError as e:
#                 if e.errno != errno.ENOENT:  # Ignore "directory not found" errors
#                     print(f"OS error deleting {directory}: {e}. Retrying ({attempt + 1}/{retries})...")
#                     time.sleep(delay)
#         print(f"⚠️ Failed to delete {directory} after {retries} attempts. Manual cleanup may be required.")

#     # Initialize local_repo as None for cleanup in case of early failure
#     local_repo = None

#     try:
#         # Clean up TEMP_DIR if it exists (unlikely since it's unique)
#         robust_rmtree(TEMP_DIR)

#         # Fetch GitHub token from DB
#         db: Session = next(get_db())
#         connections = get_user_connections_by_type(db, user_id, "github")
#         if not connections:
#             raise ValueError("❌ No GitHub connection found for user")

#         connection = connections[0]
#         connection_data = json.loads(connection.connection_json)
#         github_token = next((item["value"] for item in connection_data if item["key"] == "GITHUB_TOKEN"), None)
#         if not github_token:
#             raise ValueError("❌ GitHub token is incomplete")

#         # Initialize GitHub client
#         github = Github(github_token)
#         repo_name = github_url.split("github.com/")[1].replace('.git', '')
#         repo = github.get_repo(repo_name)

#         # Initialize MinIO client
#         minio_client = Minio(
#             "storage.clouvix.com",
#             access_key="clouvix@gmail.com",
#             secret_key="Clouvix@bangalore2025",
#             secure=True
#         )

#         # Prepare bucket and folder names
#         bucket_name = f"terraform-workspaces-user-{user_id}"
#         folder_name = f"{project_name}_terraform"

#         # Download .tf files from MinIO bucket
#         print(f"📥 Downloading .tf files from bucket: {bucket_name}, prefix: {folder_name}/")
#         files_found = False
#         for obj in minio_client.list_objects(bucket_name, prefix=f"{folder_name}/", recursive=True):
#             object_key = obj.object_name
#             if object_key.endswith('.tf'):  # Only download .tf files
#                 relative_path = object_key[len(folder_name) + 1:]
#                 local_path = os.path.join(download_path, relative_path)
#                 os.makedirs(os.path.dirname(local_path), exist_ok=True)
#                 minio_client.fget_object(bucket_name, object_key, local_path)
#                 print(f"⬇️  {object_key} -> {local_path}")
#                 files_found = True

#         if not files_found:
#             return f"❌ No .tf files found in `{folder_name}/` of bucket `{bucket_name}`."

#         # Prepare temporary repository directory
#         os.makedirs(TEMP_DIR, exist_ok=True)
#         print(f"Created temporary repository directory: {TEMP_DIR}")

#         # Clone repository
#         print(f"Cloning repository from {github_url} to {TEMP_DIR}")
#         try:
#             local_repo = Repo.clone_from(github_url, TEMP_DIR)
#         except Exception as e:
#             raise Exception(f"Failed to clone repository: {str(e)}")
#         default_branch = repo.get_branch(repo.default_branch).name
#         print(f"Default branch: {default_branch}")

#         # Create and switch to new branch locally
#         branch_name = "terraform-addition"
#         print(f"Creating and switching to branch: {branch_name}")
#         try:
#             # Check if branch exists remotely and delete it
#             try:
#                 repo.get_branch(branch_name)
#                 ref = repo.get_git_ref(f"heads/{branch_name}")
#                 ref.delete()
#                 print(f"Deleted existing remote branch: {branch_name}")
#             except:
#                 pass

#             # Create new branch locally from default branch
#             local_repo.git.checkout(default_branch)
#             local_repo.git.branch(branch_name)
#             local_repo.git.checkout(branch_name)
#             print(f"Successfully checked out new branch: {branch_name}")
#         except Exception as e:
#             raise Exception(f"Failed to create or checkout branch {branch_name}: {str(e)}")

#         # Copy .tf files to the repository
#         terraform_dir = os.path.join(TEMP_DIR, "terraform")
#         os.makedirs(terraform_dir, exist_ok=True)
#         for root, _, files in os.walk(download_path):
#             for filename in files:
#                 if filename.endswith('.tf'):
#                     src_path = os.path.join(root, filename)
#                     relative_path = os.path.relpath(src_path, download_path)
#                     dest_path = os.path.join(terraform_dir, relative_path)
#                     os.makedirs(os.path.dirname(dest_path), exist_ok=True)
#                     shutil.copy(src_path, dest_path)
#                     print(f"📄 Copied {relative_path} to {dest_path}")

#         # Commit and push changes
#         print("Committing and pushing changes...")
#         local_repo.git.add("terraform/")
#         if local_repo.is_dirty():
#             local_repo.git.commit(m="Add Terraform configuration files")
#             print("Changes committed.")
#         else:
#             return "No changes to commit; .tf files may already exist in the repository."

#         local_repo.git.push(f"https://{github_token}@github.com/{repo_name}.git", branch_name, force=True)
#         print(f"Pushed branch {branch_name} to remote repository.")

#         # Create pull request
#         print("Creating pull request...")
#         pr = repo.create_pull(
#             title="Add Terraform Configurations",
#             body="Added Terraform configuration files from provided MinIO bucket.",
#             head=branch_name,
#             base=default_branch
#         )
#         pr_url = pr.html_url
#         print(f"Pull request created: {pr_url}")
#         return f"Pull request created successfully: {pr_url}"

#     except S3Error as e:
#         error_msg = f"❌ MinIO error: {str(e)}"
#         print(error_msg)
#         return error_msg
#     except ValueError as e:
#         error_msg = str(e)
#         print(error_msg)
#         return error_msg
#     except Exception as e:
#         error_msg = f"Failed to create pull request: {str(e)}"
#         print(error_msg)
#         return error_msg
#     finally:
#         # Clean up Git repository explicitly
#         if local_repo is not None:
#             try:
#                 local_repo.close()
#                 print("Closed Git repository to release any file handles.")
#             except:
#                 pass

#         # Clean up directories
#         robust_rmtree(TEMP_DIR)
#         robust_rmtree(temp_dir)




from typing import List
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import os
import requests
import time
from jwt import encode as jwt_encode
from minio import Minio
import tempfile
import shutil
import base64
from sqlalchemy.sql import text
from sqlalchemy.exc import SQLAlchemyError

# Constants
DATABASE_URL = os.getenv("DATABASE_URL")
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
# INSTALLATION_ID = "74599310"
GITHUB_API_URL = "https://api.github.com"
# PRIVATE_KEY_PATH = r"F:\\Clouvix\\backend\\websockets-fastapi\\shreyas-clouvix.2025-07-04.private-key.pem"
MINIO_ENDPOINT = "storage.clouvix.com"
MINIO_ACCESS_KEY = "clouvix@gmail.com"
MINIO_SECRET_KEY = "Clouvix@bangalore2025"

GITHUB_PRIVATE_KEY = os.getenv("GITHUB_PRIVATE_KEY")

# # SQLAlchemy setup
# engine = create_engine(DATABASE_URL)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# def load_private_key() -> str:
#     print(f"🔍 Loading private key from file: {PRIVATE_KEY_PATH}")
#     with open(PRIVATE_KEY_PATH, "r") as f:
#         private_key = f.read()
#         print("🔐 ✅ Private key successfully loaded.")
#         return private_key

def generate_jwt(private_key: str) -> str:
    print("🔐 Generating JWT token...")
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + (10 * 60),
        "iss": GITHUB_APP_ID
    }
    jwt_token = jwt_encode(payload, private_key, algorithm="RS256")
    print("🔐 ✅ JWT generated.")
    return jwt_token

def get_installation_token(private_key: str, installation_id: str) -> str:
    jwt_token = generate_jwt(private_key)
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    url = f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens"
    print(f"🔁 Fetching installation token from: {url}")
    res = requests.post(url, headers=headers)
    print(f"📥 Token response status: {res.status_code}")
    if res.status_code == 201:
        token = res.json().get("token")
        print("✅ Installation token retrieved.")
        return token
    print(f"❌ Token response body: {res.text}")
    raise Exception(f"❌ Failed to get installation token: {res.status_code} - {res.text}")

def get_installation_info(jwt_token: str, installation_id: str) -> str:
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    url = f"{GITHUB_API_URL}/app/installations/{installation_id}"
    print(f"🔍 Fetching installation account info for installation_id: {installation_id}")
    res = requests.get(url, headers=headers)
    print(f"📥 Installation account response code: {res.status_code}")
    if res.status_code != 200:
        print(f"❌ Installation info response body: {res.text}")
        raise Exception(f"❌ Failed to get installation info: {res.status_code} - {res.text}")
    return res.json()["account"]["login"]

def validate_project_exists(minio_client, bucket_name: str, project_name: str) -> bool:
    """Check if a project exists in the MinIO bucket"""
    try:
       # new_project_name=f"{project_name}_terraform"
        prefix = f"{project_name}/"
        objects = list(minio_client.list_objects(bucket_name, prefix=prefix, recursive=True))
        return len(objects) > 0
    except Exception as e:
        print(f"❌ Error checking project existence: {str(e)}")
        return False

def list_available_projects(minio_client, bucket_name: str) -> List[str]:
    """List all available projects in the MinIO bucket"""
    try:
        # List only top-level folders
        objects = list(minio_client.list_objects(bucket_name, recursive=False))
        projects = []
        for obj in objects:
            if obj.object_name.endswith('/'):
                project_name = obj.object_name.rstrip('/')
                # Remove "_terraform" suffix if it exists
                if project_name.endswith('_terraform'):
                    project_name = project_name[:-10]  # removes last 10 characters
                projects.append(project_name)
        return projects
    except Exception as e:
        print(f"❌ Error listing projects: {str(e)}")
        return []

@tool
def fetch_tf_files_from_repo(repo_name: str, config: RunnableConfig) -> str:
    """
    Fetch all .tf files from a GitHub repo using GitHub App installation token.
    """
    print("\U0001F527 Tool: fetch_tf_files_from_repo called")
    user_id = config.get("configurable", {}).get("user_id", "unknown")
    print(f"\U0001F4E5 Inputs -> repo_name: {repo_name}, user_id: {user_id}")

    if not repo_name:
        return "❌ Repository name is required."
    if user_id == "unknown":
        return "❌ User ID is missing from config."

    try:
        # private_key = load_private_key()
        private_key = GITHUB_PRIVATE_KEY
        if not private_key:
            return "❌ GitHub private key not found in environment variables."

        jwt_token = generate_jwt(private_key)
        if not DATABASE_URL:
            return "❌ Error: DATABASE_URL not found in .env file. Cannot fetch installation ID."

        github_installation_id = None
        try:
            # Create a SQLAlchemy engine
            engine = create_engine(DATABASE_URL)

            # Establish a connection using 'with' for automatic closing
            with engine.connect() as connection:
                # Prepare the query as a text object for SQLAlchemy
                query = text("""
                SELECT connection_json
                FROM connections
                WHERE userid = :user_id AND type = 'github';
                """)
                
                # Execute the query with named parameters (SQLAlchemy's preferred way)
                result = connection.execute(query, {"user_id": user_id})

                found_ids = []
                for row in result:
                    json_data = row.connection_json # Access by column name

                    if isinstance(json_data, list):
                        for item in json_data:
                            if isinstance(item, dict) and item.get('key') == 'GITHUB_INSTALL_ID':
                                found_ids.append(item.get('value'))
                    elif isinstance(json_data, dict) and json_data.get('key') == 'GITHUB_INSTALL_ID':
                        found_ids.append(json_data.get('value'))

                if found_ids:
                    github_installation_id = found_ids[0] # Assuming you want the first one
                    # Ensure installation ID is a string
                    github_installation_id = str(github_installation_id)
                    print(f"\U0001F4E6 Fetched GitHub Installation ID: {github_installation_id}")
                else:
                    return f"❌ No GITHUB_INSTALL_ID found for user_id={user_id} and type='github'."

        except SQLAlchemyError as e:
            return f"❌ Database error (SQLAlchemy) while fetching installation ID: {e}"
        except Exception as e:
            return f"❌ An unexpected error occurred during database operation: {e}"

        if github_installation_id is None:
            return "❌ Failed to retrieve GitHub Installation ID."
        
        # Get installation token using the installation ID
        try:
            installation_token = get_installation_token(private_key, github_installation_id)
        except Exception as e:
            return f"❌ Failed to get installation token: {str(e)}"
            
        # Get username from installation info
        try:
            username = get_installation_info(jwt_token, github_installation_id)
            print(f"✅ GitHub username: {username}")
        except Exception as e:
            return f"❌ Failed to get installation info: {str(e)}"
            
    except Exception as e:
        return f"❌ GitHub authentication failed: {str(e)}"

    headers = {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github+json"
    }

    try:
        print(f"\U0001F50D Checking if repo '{repo_name}' exists under account '{username}'")
        repo_res = requests.get(f"{GITHUB_API_URL}/repos/{username}/{repo_name}", headers=headers)
        if repo_res.status_code == 404:
            return f"❌ Repository '{repo_name}' not found for user '{username}'."
        elif repo_res.status_code != 200:
            return f"❌ Failed to access repo: {repo_res.status_code} - {repo_res.text}"
    except Exception as e:
        return f"❌ Error checking repo: {str(e)}"

    def get_tf_files(contents_url: str, path: str = "") -> List[dict]:
        try:
            url = f"{contents_url}/{path}" if path else contents_url
            contents_res = requests.get(url, headers=headers, timeout=10)
            if contents_res.status_code != 200:
                print(f"⚠️ Failed to fetch {url}")
                return []

            tf_files = []
            for item in contents_res.json():
                if item["type"] == "file" and item["name"].endswith(".tf"):
                    file_content = requests.get(item["download_url"], timeout=10).text
                    tf_files.append({
                        "name": item["name"],
                        "path": item["path"],
                        "content": file_content,
                        "size": item.get("size", 0)
                    })
                    print(f"📄 Found: {item['path']}")
                elif item["type"] == "dir":
                    tf_files.extend(get_tf_files(contents_url, item["path"]))

            return tf_files
        except Exception as e:
            print(f"❌ Error in get_tf_files: {str(e)}")
            return []

    try:
        contents_url = f"{GITHUB_API_URL}/repos/{username}/{repo_name}/contents"
        tf_files = get_tf_files(contents_url)
    except Exception as e:
        return f"❌ Error reading repo contents: {str(e)}"

    if not tf_files:
        return f"🔍 No .tf files found in '{username}/{repo_name}'."

    result = f"📄 {len(tf_files)} Terraform files found in '{username}/{repo_name}':\n\n"
    total_size = sum(f.get("size", 0) for f in tf_files)
    result += f"📦 Total size: {total_size:,} bytes\n\n"

    for f in tf_files:
        result += f"📁 {f['path']} ({f['size']} bytes)\n{'-'*50}\n{f['content']}\n{'='*60}\n\n"

    return result

@tool
def raise_pr_with_tf_code(repo_name: str, project_name: str, config: RunnableConfig) -> dict:
    """
     Creates a pull request in the provided GitHub repository with .tf files
     from the MinIO bucket for the specified project name.
    """
    print("⚙️ Tool: raise_pr_with_tf_code called")
    user_id = config.get("configurable", {}).get("user_id", "unknown")
    if not repo_name or not project_name:
        return {"error": "❌ Repository and project name are required."}
    if user_id == "unknown":
        return {"error": "❌ User ID is missing from config."}

    try:    
        # private_key = load_private_key()
        private_key = GITHUB_PRIVATE_KEY
        if not private_key:
            return {"error": "❌ GitHub private key not found in environment variables."}

        jwt_token = generate_jwt(private_key)
        
        # Fetch installation ID from database
        github_installation_id = None
        try:
            # Create a SQLAlchemy engine
            engine = create_engine(DATABASE_URL)

            # Establish a connection using 'with' for automatic closing
            with engine.connect() as connection:
                # Prepare the query as a text object for SQLAlchemy
                query = text("""
                SELECT connection_json
                FROM connections
                WHERE userid = :user_id AND type = 'github';
                """)
                
                # Execute the query with named parameters
                result = connection.execute(query, {"user_id": user_id})

                found_ids = []
                for row in result:
                    json_data = row.connection_json

                    if isinstance(json_data, list):
                        for item in json_data:
                            if isinstance(item, dict) and item.get('key') == 'GITHUB_INSTALL_ID':
                                found_ids.append(item.get('value'))
                    elif isinstance(json_data, dict) and json_data.get('key') == 'GITHUB_INSTALL_ID':
                        found_ids.append(json_data.get('value'))

                if found_ids:
                    github_installation_id = found_ids[0]
                    # Ensure installation ID is a string
                    github_installation_id = str(github_installation_id)
                    print(f"\U0001F4E6 Fetched GitHub Installation ID: {github_installation_id}")
                else:
                    return {"error": f"❌ No GITHUB_INSTALL_ID found for user_id={user_id} and type='github'."}

        except SQLAlchemyError as e:
            return {"error": f"❌ Database error (SQLAlchemy) while fetching installation ID: {e}"}
        except Exception as e:
            return {"error": f"❌ An unexpected error occurred during database operation: {e}"}
            
        if github_installation_id is None:
            return {"error": "❌ Failed to retrieve GitHub Installation ID."}
            
        # Get installation token using the installation ID
        try:
            installation_token = get_installation_token(private_key, github_installation_id)
        except Exception as e:
            return {"error": f"❌ Failed to get installation token: {str(e)}"}
            
        # Get username from installation info
        try:
            username = get_installation_info(jwt_token, github_installation_id)
            print(f"✅ GitHub username: {username}")
        except Exception as e:
            return {"error": f"❌ Failed to get installation info: {str(e)}"}
    except Exception as e:
        print(f"❌ GitHub authentication failed: {str(e)}")
        return {"error": str(e)}

    try:
        minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=True
        )
        bucket_name = f"terraform-workspaces-user-{user_id}"
        new_project_name=f"{project_name}_terraform"

        # First validate that the project exists
        if not validate_project_exists(minio_client, bucket_name, new_project_name):
            available_projects = list_available_projects(minio_client, bucket_name)
            return {
                "error": f"❌ Project '{project_name}' not found in bucket '{bucket_name}'. Available projects: {available_projects}"
            }
        
        prefix = f"{new_project_name}/"
        print(f"📥 Downloading from MinIO: {bucket_name}/{prefix}")
        
        # List objects to debug what's available
        objects = list(minio_client.list_objects(bucket_name, prefix=prefix, recursive=True))
        print(f"📋 Found {len(objects)} objects in MinIO")
        
        for obj in objects:
            print(f"🔍 Object: {obj.object_name} (size: {obj.size})")
        
        if not objects:
            # Try to list all objects in the bucket to see available projects
            all_objects = list(minio_client.list_objects(bucket_name, recursive=False))
            available_projects = [obj.object_name.rstrip('/') for obj in all_objects if obj.object_name.endswith('/')]
            print(f"📋 Available projects in bucket: {available_projects}")
            return {"error": f"❌ No files found in MinIO bucket {bucket_name} with prefix {prefix}. Available projects: {available_projects}"}
        
        temp_dir = tempfile.mkdtemp()
        print(f"📁 Created temporary directory: {temp_dir}")
        
        downloaded_files = []
        for obj in objects:
            # Skip if it's a folder (ends with /)
            if obj.object_name.endswith('/'):
                print(f"⏭️ Skipping folder: {obj.object_name}")
                continue
                
            rel_path = obj.object_name[len(prefix):]
            if not rel_path:  # Skip empty relative paths
                continue
                
            download_path = os.path.join(temp_dir, rel_path)
            download_dir = os.path.dirname(download_path)
            
            # Create directory if it doesn't exist
            if download_dir and not os.path.exists(download_dir):
                os.makedirs(download_dir, exist_ok=True)
                
            # Download the file
            minio_client.fget_object(bucket_name, obj.object_name, download_path)
            downloaded_files.append(rel_path)
            print(f"⬇️ Downloaded: {obj.object_name} -> {download_path}")
            
        if not downloaded_files:
            return {"error": f"❌ No files were downloaded from MinIO. All objects were folders or empty paths."}
            
        print(f"✅ Successfully downloaded {len(downloaded_files)} files: {downloaded_files}")
        
    except Exception as e:
        print(f"❌ MinIO download failed: {str(e)}")
        return {"error": f"❌ Failed to download files from MinIO: {str(e)}"}

    headers = {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    base_url = f"{GITHUB_API_URL}/repos/{username}/{repo_name}"
    branch_name = f"clouvix-pr-{int(time.time())}"

    try:
        # Check if repository exists and is accessible
        repo_res = requests.get(base_url, headers=headers)
        if repo_res.status_code != 200:
            print(f"❌ Repository access failed: {repo_res.status_code} - {repo_res.text}")
            return {"error": f"❌ Cannot access repository {username}/{repo_name}. Status: {repo_res.status_code}"}

        # Get the default branch (might not be 'main')
        repo_data = repo_res.json()
        default_branch = repo_data.get("default_branch", "main")
        print(f"🌿 Default branch: {default_branch}")

        # Get latest commit SHA from default branch
        ref_res = requests.get(f"{base_url}/git/ref/heads/{default_branch}", headers=headers)
        if ref_res.status_code != 200:
            print(f"❌ Failed to get branch ref: {ref_res.status_code} - {ref_res.text}")
            return {"error": f"❌ Failed to get branch reference: {ref_res.status_code}"}
        
        latest_commit_sha = ref_res.json()["object"]["sha"]
        print(f"🧱 Latest commit SHA on {default_branch}: {latest_commit_sha}")

        # Get base tree SHA
        commit_res = requests.get(f"{base_url}/git/commits/{latest_commit_sha}", headers=headers)
        if commit_res.status_code != 200:
            print(f"❌ Failed to get commit: {commit_res.status_code} - {commit_res.text}")
            return {"error": f"❌ Failed to get commit details: {commit_res.status_code}"}
        
        base_tree_sha = commit_res.json()["tree"]["sha"]
        print(f"🌲 Base tree SHA from latest commit: {base_tree_sha}")

        # Create new branch
        branch_res = requests.post(f"{base_url}/git/refs", headers=headers, json={
            "ref": f"refs/heads/{branch_name}",
            "sha": latest_commit_sha
        })
        if branch_res.status_code not in [200, 201]:
            print(f"❌ Failed to create branch: {branch_res.status_code} - {branch_res.text}")
            return {"error": f"❌ Failed to create branch: {branch_res.status_code}"}
        
        print(f"🌿 Created branch: {branch_name}")

        # Create blobs for all files
        blob_sha_list = []
        for root, _, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, temp_dir).replace("\\", "/")
                
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except UnicodeDecodeError:
                    # Handle binary files
                    with open(file_path, "rb") as f:
                        content = base64.b64encode(f.read()).decode("utf-8")
                        encoding = "base64"
                else:
                    encoding = "utf-8"
                
                blob_res = requests.post(f"{base_url}/git/blobs", headers=headers, json={
                    "content": content,
                    "encoding": encoding
                })
                
                if blob_res.status_code not in [200, 201]:
                    print(f"❌ Failed to create blob for {rel_path}: {blob_res.status_code} - {blob_res.text}")
                    continue
                
                blob_sha = blob_res.json()["sha"]
                blob_sha_list.append({
                    "path": rel_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha
                })
                print(f"📄 Created blob for: {rel_path}")

        if not blob_sha_list:
            return {"error": "❌ No files were successfully processed"}

        # Create tree
        tree_res = requests.post(f"{base_url}/git/trees", headers=headers, json={
            "base_tree": base_tree_sha,
            "tree": blob_sha_list
        })
        
        if tree_res.status_code not in [200, 201]:
            print(f"❌ Failed to create tree: {tree_res.status_code} - {tree_res.text}")
            return {"error": f"❌ Failed to create tree: {tree_res.status_code}"}
        
        tree_sha = tree_res.json()["sha"]
        print(f"🌲 Created tree: {tree_sha}")

        # Create commit
        commit_message = f"[ClouVix] Upload Terraform files for {project_name}"
        new_commit_res = requests.post(f"{base_url}/git/commits", headers=headers, json={
            "message": commit_message,
            "tree": tree_sha,
            "parents": [latest_commit_sha]
        })
        
        if new_commit_res.status_code not in [200, 201]:
            print(f"❌ Failed to create commit: {new_commit_res.status_code} - {new_commit_res.text}")
            return {"error": f"❌ Failed to create commit: {new_commit_res.status_code}"}
        
        new_commit_sha = new_commit_res.json()["sha"]
        print(f"📝 Created commit: {new_commit_sha}")

        # Update branch reference
        ref_update_res = requests.patch(f"{base_url}/git/refs/heads/{branch_name}", headers=headers, json={
            "sha": new_commit_sha,
            "force": True
        })
        
        if ref_update_res.status_code not in [200, 201]:
            print(f"❌ Failed to update branch reference: {ref_update_res.status_code} - {ref_update_res.text}")
            return {"error": f"❌ Failed to update branch reference: {ref_update_res.status_code}"}
        
        print(f"🔄 Updated branch reference: {branch_name}")

        # Create pull request
        pr_body = f"""This PR includes Terraform files uploaded from the ClouVix platform.

**Project:** {project_name}
**Files uploaded:** {len(blob_sha_list)} files

Generated automatically by ClouVix."""

        pr_res = requests.post(f"{base_url}/pulls", headers=headers, json={
            "title": f"[ClouVix] Upload Terraform files for {project_name}",
            "head": branch_name,
            "base": default_branch,
            "body": pr_body
        })

        if pr_res.status_code not in [200, 201]:
            print(f"❌ Failed to create pull request: {pr_res.status_code} - {pr_res.text}")
            return {"error": f"❌ Failed to create pull request: {pr_res.status_code} - {pr_res.text}"}

        pr_data = pr_res.json()
        pr_url = pr_data.get("html_url", "")
        pr_number = pr_data.get("number", "")
        
        print(f"✅ Pull request created successfully: #{pr_number}")
        
        return {
            "reply": f"✅ Pull Request #{pr_number} created successfully for project '{project_name}' on repo '{username}/{repo_name}'",
            "url": pr_url,
            "branch": branch_name,
            "files_uploaded": len(blob_sha_list),
            "suggestions": [
                "Click the link above to review the PR",
                "Merge it into main if everything looks good",
                "Let me know if you want to trigger terraform apply"
            ]
        }

    except Exception as e:
        print(f"❌ GitHub operation failed: {str(e)}")
        return {"error": f"❌ GitHub operation failed: {str(e)}"}

    finally:
        # Clean up temporary directory
        if 'temp_dir' in locals():
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"🧹 Cleaned up temporary directory: {temp_dir}")