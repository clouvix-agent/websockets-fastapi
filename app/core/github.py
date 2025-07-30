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
# MINIO_ENDPOINT = "storage.clouvix.com"
# MINIO_ACCESS_KEY = "clouvix@gmail.com"
# MINIO_SECRET_KEY = "Clouvix@bangalore2025"

GITHUB_PRIVATE_KEY = os.getenv("GITHUB_PRIVATE_KEY")


from app.db.connection import get_user_connections_by_type 
from app.models.connection import Connection
from app.routers.github import get_github_installation_id

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

GITHUB_API_URL = "https://api.github.com"

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


# @tool
# def raise_pr_with_tf_code(repo_name: str, project_name: str, tf_code: str, config: RunnableConfig) -> dict:
#     """
#     Raises a pull request with generated Terraform code into the given GitHub repository.
#     """

#     print("🔍 Raising PR with TF code...")
#     user_id = config.get("configurable", {}).get("user_id", "unknown")
#     if not repo_name or not project_name or not tf_code:
#         return {"error": "❌ repo_name, project_name, and tf_code are required."}
#     if user_id == "unknown":
#         return {"error": "❌ User ID is missing from config."}

#     # --- Load and fix GitHub App private key ---
#     private_key_raw = os.getenv("GITHUB_PRIVATE_KEY")
#     if not private_key_raw:
#         return {"error": "❌ GITHUB_PRIVATE_KEY not found in environment variables."}
#     PRIVATE_KEY = private_key_raw.strip()
#     if "-----BEGIN RSA PRIVATE KEY-----" not in PRIVATE_KEY:
#         PRIVATE_KEY = f"-----BEGIN RSA PRIVATE KEY-----\n{PRIVATE_KEY}\n-----END RSA PRIVATE KEY-----"

#     try:
#         jwt_token = generate_jwt(PRIVATE_KEY)

#         # --- Get GitHub installation ID ---
#         github_installation_id = get_github_installation_id(int(user_id))
#         if not github_installation_id:
#             return {"error": f"❌ No GitHub installation ID found for user_id={user_id}"}

#         github_installation_id = str(github_installation_id)
#         print(f"🔍 GitHub installation ID: {github_installation_id}")

#         installation_token = get_installation_token(PRIVATE_KEY, github_installation_id)
#         username = get_installation_info(jwt_token, github_installation_id)

#         headers = {
#             "Authorization": f"Bearer {installation_token}",
#             "Accept": "application/vnd.github+json"
#         }

#         # Parse repo name
#         base_url = f"{GITHUB_API_URL}/repos/{repo_name}"
#         print(f"🔍 Base URL: {base_url}")

#         # --- Check repo access ---
#         repo_res = requests.get(base_url, headers=headers)
#         if repo_res.status_code != 200:
#             return {"error": f"❌ Cannot access repo '{repo_name}': {repo_res.status_code} - {repo_res.text}"}

#         repo_data = repo_res.json()
#         default_branch = repo_data.get("default_branch", "main")
#         print(f"🌿 Default branch reported by GitHub: {default_branch}")

#         # --- Get latest commit SHA ---
#         ref_url = f"{base_url}/git/ref/heads/{default_branch}"
#         ref_res = requests.get(ref_url, headers=headers)

#         if ref_res.status_code == 404 and default_branch == "main":
#             print("⚠️ Branch 'main' not found. Trying 'master' as fallback...")
#             default_branch = "master"
#             ref_url = f"{base_url}/git/ref/heads/{default_branch}"
#             ref_res = requests.get(ref_url, headers=headers)

#         if ref_res.status_code != 200:
#             return {"error": f"❌ Failed to get branch ref: {ref_res.status_code} - {ref_res.text}"}

#         ref_json = ref_res.json()
#         if "object" not in ref_json or "sha" not in ref_json["object"]:
#             return {"error": f"❌ Invalid ref structure: {ref_json}"}

#         latest_commit_sha = ref_json["object"]["sha"]
#         print(f"🧱 Latest commit SHA: {latest_commit_sha}")

#         # --- Get base tree SHA ---
#         commit_res = requests.get(f"{base_url}/git/commits/{latest_commit_sha}", headers=headers)
#         if commit_res.status_code != 200:
#             return {"error": f"❌ Failed to get commit: {commit_res.status_code} - {commit_res.text}"}
#         base_tree_sha = commit_res.json()["tree"]["sha"]

#         # --- Create branch ---
#         branch_name = f"clouvix-pr-{int(time.time())}"
#         branch_res = requests.post(f"{base_url}/git/refs", headers=headers, json={
#             "ref": f"refs/heads/{branch_name}",
#             "sha": latest_commit_sha
#         })
#         if branch_res.status_code not in [200, 201]:
#             return {"error": f"❌ Failed to create branch: {branch_res.status_code} - {branch_res.text}"}
#         print(f"🌿 Created new branch: {branch_name}")

#         # --- Create blob ---
#         blob_res = requests.post(f"{base_url}/git/blobs", headers=headers, json={
#             "content": tf_code,
#             "encoding": "utf-8"
#         })
#         if blob_res.status_code not in [200, 201]:
#             return {"error": f"❌ Failed to create blob: {blob_res.status_code} - {blob_res.text}"}
#         blob_sha = blob_res.json()["sha"]

#         # --- Create tree ---
#         tree_res = requests.post(f"{base_url}/git/trees", headers=headers, json={
#             "base_tree": base_tree_sha,
#             "tree": [{
#                 "path": "main.tf",
#                 "mode": "100644",
#                 "type": "blob",
#                 "sha": blob_sha
#             }]
#         })
#         if tree_res.status_code not in [200, 201]:
#             return {"error": f"❌ Failed to create tree: {tree_res.status_code} - {tree_res.text}"}
#         tree_sha = tree_res.json()["sha"]

#         # --- Create commit ---
#         commit_res = requests.post(f"{base_url}/git/commits", headers=headers, json={
#             "message": f"[ClouVix] Add Terraform for {project_name}",
#             "tree": tree_sha,
#             "parents": [latest_commit_sha]
#         })
#         if commit_res.status_code not in [200, 201]:
#             return {"error": f"❌ Failed to create commit: {commit_res.status_code} - {commit_res.text}"}
#         new_commit_sha = commit_res.json()["sha"]

#         # --- Update ref ---
#         update_res = requests.patch(f"{base_url}/git/refs/heads/{branch_name}", headers=headers, json={
#             "sha": new_commit_sha,
#             "force": True
#         })
#         if update_res.status_code not in [200, 201]:
#             return {"error": f"❌ Failed to update branch ref: {update_res.status_code} - {update_res.text}"}

#         # --- Create PR ---
#         pr_body = f"""This PR includes Terraform code for **{project_name}**.\n\nGenerated by ClouVix assistant."""
#         pr_res = requests.post(f"{base_url}/pulls", headers=headers, json={
#             "title": f"[ClouVix] Terraform code for {project_name}",
#             "head": branch_name,
#             "base": default_branch,
#             "body": pr_body
#         })
#         print(f"📤 PR creation response: {pr_res.status_code} - {pr_res.text}")

#         if pr_res.status_code not in [200, 201]:
#             return {"error": f"❌ Failed to create PR: {pr_res.status_code} - {pr_res.text}"}

#         pr_url = pr_res.json().get("html_url", "")
#         return {
#             "reply": f"✅ Pull Request created successfully for '{project_name}' in repo '{repo_name}'",
#             "url": pr_url,
#             "branch": branch_name,
#             "suggestions": [
#                 "Click the PR link to review the Terraform code",
#                 "Merge it once reviewed",
#                 "Let me know if you want to apply the changes"
#             ]
#         }

#     except Exception as e:
#         return {"error": f"❌ Failed to raise PR: {str(e)}"}    



# @tool
# def yaml_file_raise_pr(repo_name:str,config: RunnableConfig):
#     "Raises a pull request for github action file or YAML file by taking github repo name as input "
#     print("Inside the yaml file raise pr function.")
#     user_id = config.get("configurable", {}).get("user_id", "unknown")
#     if not repo_name:
#         return {"error": "❌ repo_name is required."}
#     if user_id == "unknown":
#         return {"error": "❌ User ID is missing from config."}

#     # --- Load and fix GitHub App private key ---
#     private_key_raw = os.getenv("GITHUB_PRIVATE_KEY")
#     if not private_key_raw:
#         return {"error": "❌ GITHUB_PRIVATE_KEY not found in environment variables."}
#     PRIVATE_KEY = private_key_raw.strip()
#     if "-----BEGIN RSA PRIVATE KEY-----" not in PRIVATE_KEY:
#         PRIVATE_KEY = f"-----BEGIN RSA PRIVATE KEY-----\n{PRIVATE_KEY}\n-----END RSA PRIVATE KEY-----"

#     try:
#         jwt_token = generate_jwt(PRIVATE_KEY)

#         # --- Get GitHub installation ID ---
#         github_installation_id = get_github_installation_id(int(user_id))
#         if not github_installation_id:
#             return {"error": f"❌ No GitHub installation ID found for user_id={user_id}"}

#         github_installation_id = str(github_installation_id)
#         print(f"🔍 GitHub installation ID: {github_installation_id}")

#         installation_token = get_installation_token(PRIVATE_KEY, github_installation_id)
#         username = get_installation_info(jwt_token, github_installation_id)

#         headers = {
#             "Authorization": f"Bearer {installation_token}",
#             "Accept": "application/vnd.github+json"
#         }


def raise_github_pr(user_id: int, repo_name: str, pr_title: str, pr_body: str, files: dict[str, str]) -> dict:
    """
    Generic utility to raise a GitHub PR for a given user and repo.

    Args:
        user_id (int): ID of the user (used to fetch GitHub install ID)
        repo_name (str): Full repo name e.g. "username/repo"
        pr_title (str): Title of the pull request
        pr_body (str): Body/description of the pull request
        files (dict): Dictionary of file_path => file_content

    Returns:
        dict: Response object with PR URL and branch or error
    """
    # --- Load and fix GitHub App private key ---
    private_key_raw = os.getenv("GITHUB_PRIVATE_KEY")
    if not private_key_raw:
        return {"error": "❌ GITHUB_PRIVATE_KEY not found in environment variables."}

    private_key = private_key_raw.strip()
    if "-----BEGIN RSA PRIVATE KEY-----" not in private_key:
        private_key = f"-----BEGIN RSA PRIVATE KEY-----\n{private_key}\n-----END RSA PRIVATE KEY-----"

    try:
        # --- Auth ---
        jwt_token = generate_jwt(private_key)
        github_installation_id = get_github_installation_id(user_id)
        if not github_installation_id:
            return {"error": f"❌ No GitHub installation ID found for user_id={user_id}"}
        github_installation_id = str(github_installation_id)

        installation_token = get_installation_token(private_key, github_installation_id)
        username = get_installation_info(jwt_token, github_installation_id)

        headers = {
            "Authorization": f"Bearer {installation_token}",
            "Accept": "application/vnd.github+json"
        }

        base_url = f"{GITHUB_API_URL}/repos/{repo_name}"

        # --- Verify repo access ---
        repo_res = requests.get(base_url, headers=headers)
        if repo_res.status_code != 200:
            return {"error": f"❌ Cannot access repo '{repo_name}': {repo_res.status_code} - {repo_res.text}"}

        default_branch = repo_res.json().get("default_branch", "main")

        # --- Get latest commit SHA ---
        ref_url = f"{base_url}/git/ref/heads/{default_branch}"
        ref_res = requests.get(ref_url, headers=headers)

        if ref_res.status_code == 404 and default_branch == "main":
            default_branch = "master"
            ref_url = f"{base_url}/git/ref/heads/{default_branch}"
            ref_res = requests.get(ref_url, headers=headers)

        if ref_res.status_code != 200:
            return {"error": f"❌ Failed to get branch ref: {ref_res.status_code} - {ref_res.text}"}

        latest_commit_sha = ref_res.json()["object"]["sha"]

        # --- Get base tree SHA ---
        commit_res = requests.get(f"{base_url}/git/commits/{latest_commit_sha}", headers=headers)
        if commit_res.status_code != 200:
            return {"error": f"❌ Failed to get commit: {commit_res.status_code} - {commit_res.text}"}
        base_tree_sha = commit_res.json()["tree"]["sha"]

        # --- Create new branch ---
        branch_name = f"clouvix-pr-{int(time.time())}"
        branch_res = requests.post(f"{base_url}/git/refs", headers=headers, json={
            "ref": f"refs/heads/{branch_name}",
            "sha": latest_commit_sha
        })
        if branch_res.status_code not in [200, 201]:
            return {"error": f"❌ Failed to create branch: {branch_res.status_code} - {branch_res.text}"}

        # --- Upload blobs for all files ---
        tree_items = []
        for file_path, file_content in files.items():
            blob_res = requests.post(f"{base_url}/git/blobs", headers=headers, json={
                "content": file_content,
                "encoding": "utf-8"
            })
            if blob_res.status_code not in [200, 201]:
                return {"error": f"❌ Failed to create blob for '{file_path}': {blob_res.status_code} - {blob_res.text}"}
            blob_sha = blob_res.json()["sha"]
            tree_items.append({
                "path": file_path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha
            })

        # --- Create tree ---
        tree_res = requests.post(f"{base_url}/git/trees", headers=headers, json={
            "base_tree": base_tree_sha,
            "tree": tree_items
        })
        if tree_res.status_code not in [200, 201]:
            return {"error": f"❌ Failed to create tree: {tree_res.status_code} - {tree_res.text}"}
        tree_sha = tree_res.json()["sha"]

        # --- Create commit ---
        commit_res = requests.post(f"{base_url}/git/commits", headers=headers, json={
            "message": pr_title,
            "tree": tree_sha,
            "parents": [latest_commit_sha]
        })
        if commit_res.status_code not in [200, 201]:
            return {"error": f"❌ Failed to create commit: {commit_res.status_code} - {commit_res.text}"}
        commit_sha = commit_res.json()["sha"]

        # --- Update branch ref ---
        ref_update_res = requests.patch(f"{base_url}/git/refs/heads/{branch_name}", headers=headers, json={
            "sha": commit_sha,
            "force": True
        })
        if ref_update_res.status_code not in [200, 201]:
            return {"error": f"❌ Failed to update branch: {ref_update_res.status_code} - {ref_update_res.text}"}

        # --- Create PR ---
        pr_res = requests.post(f"{base_url}/pulls", headers=headers, json={
            "title": pr_title,
            "head": branch_name,
            "base": default_branch,
            "body": pr_body
        })
        if pr_res.status_code not in [200, 201]:
            return {"error": f"❌ Failed to create PR: {pr_res.status_code} - {pr_res.text}"}

        pr_url = pr_res.json().get("html_url")
        return {
            "reply": f"✅ Pull Request created: {pr_title}",
            "url": pr_url,
            "branch": branch_name
        }

    except Exception as e:
        return {"error": f"❌ Exception while raising PR: {str(e)}"}


@tool
def raise_pr_with_tf_code(repo_name: str, project_name: str, tf_code: str, config: RunnableConfig) -> dict:
    """
    Tool: Raises a pull request to a GitHub repo with the provided Terraform code as 'main.tf'.
    """

    print("🚀 Tool: raise_pr_with_tf_code called")
    user_id = config.get("configurable", {}).get("user_id", "unknown")
    if not repo_name or not project_name or not tf_code:
        return {"error": "❌ repo_name, project_name, and tf_code are required."}
    if user_id == "unknown":
        return {"error": "❌ User ID is missing from config."}

    try:
        # Prepare PR metadata
        pr_title = f"[ClouVix] Terraform code for {project_name}"
        pr_body = f"This PR includes Terraform code for **{project_name}**.\n\nGenerated automatically by ClouVix Assistant."
        files = {
            "main.tf": tf_code  # Single file
        }

        # Call reusable function
        result = raise_github_pr(
            user_id=int(user_id),
            repo_name=repo_name,
            pr_title=pr_title,
            pr_body=pr_body,
            files=files
        )

        return result

    except Exception as e:
        return {"error": f"❌ Exception while raising PR: {str(e)}"}


@tool
def yaml_file_raise_pr(repo_name: str, config: RunnableConfig) -> dict:
    """
    Tool: Raises a pull request to add a GitHub Actions workflow using the 'clouvix.yml' file.
    The file is pushed to '.github/workflows/clouvix.yml' in the specified repository.
    """

    print("🚀 Tool: yaml_file_raise_pr called")
    user_id = config.get("configurable", {}).get("user_id", "unknown")
    if not repo_name:
        return {"error": "❌ repo_name is required."}
    if user_id == "unknown":
        return {"error": "❌ User ID is missing from config."}

    # Load the clouvix.yml file
    try:
        with open("app\core\clouvix.yml", "r", encoding="utf-8") as f:
            yaml_content = f.read()
    except FileNotFoundError:
        return {"error": "❌ 'clouvix.yml' file not found in the current directory."}
    except Exception as e:
        return {"error": f"❌ Failed to read clouvix.yml: {str(e)}"}

    try:
        pr_title = "[ClouVix] Add GitHub Actions workflow"
        pr_body = (
            "This PR adds a GitHub Actions workflow for automation.\n\n"
            "File: `.github/workflows/clouvix.yml`\n\n"
            "Generated automatically by ClouVix Assistant."
        )
        files = {
            ".github/workflows/clouvix.yml": yaml_content
        }

        result = raise_github_pr(
            user_id=int(user_id),
            repo_name=repo_name,
            pr_title=pr_title,
            pr_body=pr_body,
            files=files
        )

        return result

    except Exception as e:
        return {"error": f"❌ Exception while raising YAML PR: {str(e)}"}