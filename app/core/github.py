import os
import shutil
import json
import tempfile
import time
import errno
import stat
from github import Github
from git import Repo
from langchain_core.runnables import RunnableConfig
from app.db.connection import get_user_connections_by_type
from app.database import get_db
from sqlalchemy.orm import Session
from langchain.tools import tool
from minio import Minio
from minio.error import S3Error

@tool
def create_pr(github_url: str, project_name: str, config: RunnableConfig) -> str:
    """
    Creates a pull request in the provided GitHub repository with .tf files
    from the MinIO bucket for the specified project name.
    """
    print("Creating pull request with .tf files...")
    user_id = config['configurable'].get('user_id', 'unknown')

    # Input validation
    if not github_url:
        return "Error: GitHub repository URL is required."
    if not project_name:
        return "Error: Project name is required."
    if not user_id:
        return "Error: User ID is required."

    # Use a unique temporary directory for temp_repo to avoid conflicts
    TEMP_DIR = os.path.join(tempfile.gettempdir(), f"temp_repo_{int(time.time())}")
    temp_dir = tempfile.mkdtemp()
    download_path = os.path.join(temp_dir, f"{project_name}_terraform")
    os.makedirs(download_path, exist_ok=True)

    def force_remove_readonly(func, path, excinfo):
        """Handle read-only files by changing permissions and retrying deletion."""
        os.chmod(path, stat.S_IWRITE)
        func(path)

    def robust_rmtree(directory, retries=5, delay=1):
        """Attempt to remove a directory with retries, handling permission issues and locks."""
        if not os.path.exists(directory):
            print(f"🧹 Directory {directory} does not exist, no cleanup needed.")
            return
        for attempt in range(retries):
            try:
                shutil.rmtree(directory, onerror=force_remove_readonly)
                print(f"🧹 Successfully deleted directory: {directory}")
                return
            except PermissionError as e:
                print(f"Permission error deleting {directory}: {e}. Retrying ({attempt + 1}/{retries})...")
                time.sleep(delay)
            except OSError as e:
                if e.errno != errno.ENOENT:  # Ignore "directory not found" errors
                    print(f"OS error deleting {directory}: {e}. Retrying ({attempt + 1}/{retries})...")
                    time.sleep(delay)
        print(f"⚠️ Failed to delete {directory} after {retries} attempts. Manual cleanup may be required.")

    # Initialize local_repo as None for cleanup in case of early failure
    local_repo = None

    try:
        # Clean up TEMP_DIR if it exists (unlikely since it’s unique)
        robust_rmtree(TEMP_DIR)

        # Fetch GitHub token from DB
        db: Session = next(get_db())
        connections = get_user_connections_by_type(db, user_id, "github")
        if not connections:
            raise ValueError("❌ No GitHub connection found for user")

        connection = connections[0]
        connection_data = json.loads(connection.connection_json)
        github_token = next((item["value"] for item in connection_data if item["key"] == "GITHUB_TOKEN"), None)
        if not github_token:
            raise ValueError("❌ GitHub token is incomplete")

        # Initialize GitHub client
        github = Github(github_token)
        repo_name = github_url.split("github.com/")[1].replace('.git', '')
        repo = github.get_repo(repo_name)

        # Initialize MinIO client
        minio_client = Minio(
            "storage.clouvix.com",
            access_key="clouvix@gmail.com",
            secret_key="Clouvix@bangalore2025",
            secure=True
        )

        # Prepare bucket and folder names
        bucket_name = f"terraform-workspaces-user-{user_id}"
        folder_name = f"{project_name}_terraform"

        # Download .tf files from MinIO bucket
        print(f"📥 Downloading .tf files from bucket: {bucket_name}, prefix: {folder_name}/")
        files_found = False
        for obj in minio_client.list_objects(bucket_name, prefix=f"{folder_name}/", recursive=True):
            object_key = obj.object_name
            if object_key.endswith('.tf'):  # Only download .tf files
                relative_path = object_key[len(folder_name) + 1:]
                local_path = os.path.join(download_path, relative_path)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                minio_client.fget_object(bucket_name, object_key, local_path)
                print(f"⬇️  {object_key} -> {local_path}")
                files_found = True

        if not files_found:
            return f"❌ No .tf files found in `{folder_name}/` of bucket `{bucket_name}`."

        # Prepare temporary repository directory
        os.makedirs(TEMP_DIR, exist_ok=True)
        print(f"Created temporary repository directory: {TEMP_DIR}")

        # Clone repository
        print(f"Cloning repository from {github_url} to {TEMP_DIR}")
        try:
            local_repo = Repo.clone_from(github_url, TEMP_DIR)
        except Exception as e:
            raise Exception(f"Failed to clone repository: {str(e)}")
        default_branch = repo.get_branch(repo.default_branch).name
        print(f"Default branch: {default_branch}")

        # Create and switch to new branch locally
        branch_name = "terraform-addition"
        print(f"Creating and switching to branch: {branch_name}")
        try:
            # Check if branch exists remotely and delete it
            try:
                repo.get_branch(branch_name)
                ref = repo.get_git_ref(f"heads/{branch_name}")
                ref.delete()
                print(f"Deleted existing remote branch: {branch_name}")
            except:
                pass

            # Create new branch locally from default branch
            local_repo.git.checkout(default_branch)
            local_repo.git.branch(branch_name)
            local_repo.git.checkout(branch_name)
            print(f"Successfully checked out new branch: {branch_name}")
        except Exception as e:
            raise Exception(f"Failed to create or checkout branch {branch_name}: {str(e)}")

        # Copy .tf files to the repository
        terraform_dir = os.path.join(TEMP_DIR, "terraform")
        os.makedirs(terraform_dir, exist_ok=True)
        for root, _, files in os.walk(download_path):
            for filename in files:
                if filename.endswith('.tf'):
                    src_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(src_path, download_path)
                    dest_path = os.path.join(terraform_dir, relative_path)
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy(src_path, dest_path)
                    print(f"📄 Copied {relative_path} to {dest_path}")

        # Commit and push changes
        print("Committing and pushing changes...")
        local_repo.git.add("terraform/")
        if local_repo.is_dirty():
            local_repo.git.commit(m="Add Terraform configuration files")
            print("Changes committed.")
        else:
            return "No changes to commit; .tf files may already exist in the repository."

        local_repo.git.push(f"https://{github_token}@github.com/{repo_name}.git", branch_name, force=True)
        print(f"Pushed branch {branch_name} to remote repository.")

        # Create pull request
        print("Creating pull request...")
        pr = repo.create_pull(
            title="Add Terraform Configurations",
            body="Added Terraform configuration files from provided MinIO bucket.",
            head=branch_name,
            base=default_branch
        )
        pr_url = pr.html_url
        print(f"Pull request created: {pr_url}")
        return f"Pull request created successfully: {pr_url}"

    except S3Error as e:
        error_msg = f"❌ MinIO error: {str(e)}"
        print(error_msg)
        return error_msg
    except ValueError as e:
        error_msg = str(e)
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Failed to create pull request: {str(e)}"
        print(error_msg)
        return error_msg
    finally:
        # Clean up Git repository explicitly
        if local_repo is not None:
            try:
                local_repo.close()
                print("Closed Git repository to release any file handles.")
            except:
                pass

        # Clean up directories
        robust_rmtree(TEMP_DIR)
        robust_rmtree(temp_dir)