import os
import tempfile
import shutil
from minio import Minio
from minio.error import S3Error
from langchain_core.runnables import RunnableConfig  
from langchain.tools import tool     
import subprocess
from typing import List, Optional, Dict, Tuple
from app.db.drift import fetch_drift_reason

import json
import boto3
from app.models.connection import Connection
from app.database import get_db_session
from app.db.connection import get_user_connections_by_type
from app.core.existing_to_tf import get_aws_credentials_from_db


from app.db.workspace_status import create_or_update_workspace_status
from app.schemas.workspace_status import WorkspaceStatusCreate
from app.db.drift import fetch_drift_reason, delete_drift_result

from openai import OpenAI

client = OpenAI()


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



def update_tf_file_with_llm(tf_path: str, drift_info: str, model: str = "gpt-4o-mini") -> bool:
    """
    Updates the Terraform file using LLM to reflect the drift info.

    Args:
        tf_path (str): Full path to the local main.tf file.
        drift_info (str): The drift_reason text from DB.
        model (str): OpenAI model to use (default: gpt-4o-mini)

    Returns:
        bool: True if update succeeded, False otherwise.
    """
    if not os.path.exists(tf_path):
        print(f"❌ File {tf_path} does not exist.")
        return False

    with open(tf_path, "r") as f:
        tf_content = f.read()

    system_prompt = (
        "You are an expert Terraform assistant. "
        "You are given Terraform drift output and the contents of a Terraform (.tf) file. "
        "Your job is to make minimal, precise updates to the file so that it matches the live infrastructure state described in the drift output.\n\n"
        "⚠️ VERY IMPORTANT:\n"
        "- DO NOT modify any resource, argument, value, or block unless it is explicitly mentioned in the drift output.\n"
        "- DO NOT reformat or reorganize the file.\n"
        "- DO NOT reorder attributes or resources.\n"
        "- DO NOT add or remove comments.\n"
        "- Only add new resources, remove existing ones, or make changes if they are directly described in the drift output.\n"
        "- Return ONLY the full updated .tf content, without markdown or language tags like ```hcl.\n"
    )

    user_prompt = f"""
    Here is the Terraform drift output:

    {drift_info}

    And here is the original Terraform file:

    {tf_content}

    Please update the file strictly based on the drift. Do not change anything else.
    """

    try:
        print("🤖 Contacting OpenAI GPT-4o-mini to update the .tf file...")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2
        )

        updated_code = response.choices[0].message.content

        updated_lines = updated_code.strip().splitlines()

        if updated_lines and updated_lines[0].strip().lower() in ("```hcl", "hcl", "```"):
            updated_lines = updated_lines[1:]

        if updated_lines and updated_lines[-1].strip() == "```":
            updated_lines = updated_lines[:-1]

        updated_code = "\n".join(updated_lines)

        with open(tf_path, "w") as f:
            f.write(updated_code)

        print("✅ Updated Terraform file successfully using GPT.")
        return True

    except Exception as e:
        print(f"❌ Failed to contact OpenAI or parse response: {e}")
        return False

def run_terraform_command(command: List[str],working_dir: str,env: Optional[Dict[str, str]] = None) -> Tuple[bool, str, str]:
    """
    Runs a Terraform command in a subprocess.

    Args:
        command (List[str]): Terraform command parts (e.g., ["terraform", "plan"])
        working_dir (str): Directory to run Terraform in
        env (dict, optional): Environment variables to pass

    Returns:
        Tuple:
            - success (bool): True if command executed successfully (exit code 0)
            - stdout (str): Standard output from Terraform
            - stderr (str): Standard error from Terraform
    """
    print(f"\n🚀 Running: {' '.join(command)} in {working_dir}...")

    try:
        result = subprocess.run(
            command,
            cwd=working_dir,
            capture_output=True,
            text=True,
            check=False,
            env=env
        )

        success = result.returncode == 0
        if not success:
            print(f"❌ Terraform failed with return code {result.returncode}")
            print(f"STDERR:\n{result.stderr.strip()}")

        return success, result.stdout.strip(), result.stderr.strip()

    except FileNotFoundError:
        return False, "", "❌ Terraform executable not found. Is it installed and in your PATH?"
    except Exception as e:
        return False, "", f"❌ Unexpected error running Terraform: {e}"



def download_terraform_project_from_minio(user_id: int, project_name: str) -> str:
    """
    Downloads all Terraform files for the given user/project from MinIO to a temporary directory.
    """
    bucket_name = f"terraform-workspaces-user-{user_id}"
    folder_prefix = f"{project_name}_terraform"

    temp_dir = tempfile.mkdtemp()
    local_project_dir = os.path.join(temp_dir, folder_prefix)
    os.makedirs(local_project_dir, exist_ok=True)

    try:
        minio_client = Minio(
            "storage.clouvix.com",
            access_key="clouvix@gmail.com",
            secret_key="Clouvix@bangalore2025",
            secure=True
        )

        print(f"📦 Downloading from: bucket={bucket_name}, prefix={folder_prefix}/")
        files_found = False

        for obj in minio_client.list_objects(bucket_name, prefix=f"{folder_prefix}/", recursive=True):
            object_key = obj.object_name
            relative_path = object_key[len(folder_prefix) + 1:]
            local_file_path = os.path.join(local_project_dir, relative_path)
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            minio_client.fget_object(bucket_name, object_key, local_file_path)
            print(f"⬇️  Downloaded {object_key} → {local_file_path}")
            files_found = True

        if not files_found:
            return f"❌ No files found in `{folder_prefix}/` of bucket `{bucket_name}`."

        return local_project_dir

    except S3Error as e:
        return f"❌ MinIO error: {e}"
    except Exception as e:
        return f"❌ Failed to download project: {e}"



def upload_project_to_minio(local_project_dir: str, user_id: int, project_name: str) -> str:
    """
    Uploads the updated Terraform project files (main.tf, terraform.tfstate, etc.)
    from a local folder to both MinIO and S3, excluding .terraform directory.

    Args:
        local_project_dir (str): Path to local downloaded folder (e.g., /tmp/.../myproject_terraform)
        user_id (int): User ID (used to infer bucket name)
        project_name (str): Project name (used as folder prefix)

    Returns:
        str: Success message or error string
    """
    try:
        bucket_name = f"terraform-workspaces-user-{user_id}"
        folder_name = f"{project_name}_terraform"

        print("📤 Uploading updated folder to MinIO...")

        # === MinIO Upload ===
        minio_client = Minio(
            "storage.clouvix.com",
            access_key="clouvix@gmail.com",
            secret_key="Clouvix@bangalore2025",
            secure=True
        )

        for root, _, files in os.walk(local_project_dir):
            if ".terraform" in root:
                continue

            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, local_project_dir)
                object_key = os.path.normpath(f"{folder_name}/{relative_path}").replace("\\", "/")

                minio_client.fput_object(bucket_name, object_key, file_path)
                print(f"⬆️ MinIO: {file_path} → {object_key}")

        print("✅ Upload to MinIO completed.")

        # === S3 Upload (optional) ===
        try:
            s3_config = get_s3_connection_info_with_credentials(user_id)
            s3_bucket = s3_config.get("bucket")
            s3_region = s3_config.get("region")
            s3_prefix = s3_config.get("prefix", "")
            aws_access_key_id = s3_config.get("aws_access_key_id")
            aws_secret_access_key = s3_config.get("aws_secret_access_key")

            if s3_bucket and aws_access_key_id and aws_secret_access_key:
                import boto3
                s3 = boto3.client(
                    's3',
                    region_name=s3_region,
                    aws_access_key_id=aws_access_key_id,
                    aws_secret_access_key=aws_secret_access_key
                )

                s3_object_prefix = f"{s3_prefix}{folder_name}/" if s3_prefix else f"{folder_name}/"

                for root, _, files in os.walk(local_project_dir):
                    if ".terraform" in root:
                        continue

                    for file in files:
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, local_project_dir)
                        object_key = f"{s3_object_prefix}{relative_path}".replace("\\", "/")

                        s3.upload_file(file_path, s3_bucket, object_key)
                        print(f"⬆️ S3: {file_path} → {object_key}")

                print("✅ Upload to S3 completed.")
            else:
                print("⚠️ Skipping S3 upload - missing credentials or bucket info.")
        except Exception as s3e:
            print(f"❌ Failed to upload to S3: {s3e}")

        return f"✅ Upload complete. Files synced to both MinIO and S3 (if configured): `{folder_name}/`"

    except S3Error as s3e:
        return f"❌ MinIO error: {str(s3e)}"
    except Exception as e:
        return f"❌ Upload failed: {str(e)}"




# @tool
# def drift_detection_tool(project_name: str, config: RunnableConfig, action: str):
#     """
#     This tool solves Terraform drift based on selected action:
    
#     Args:
#         project_name (str): Name of the Terraform project.
#         config (RunnableConfig): Contains `user_id` inside config["configurable"].
#         action (str): "apply_drift" to apply changes from drift, or "revert_back" to discard drift and apply original .tf file.

#     Returns:
#         str: Success or failure message.
#     """
#     user_id = config['configurable'].get('user_id', 'unknown')
#     if user_id == 'unknown':
#         return "❌ user_id not found in config['configurable']"

#     print(f"✅ User ID extracted: {user_id} for project: {project_name}")

#     local_path = None  # Define early for finally block to work

#     try:
#         local_path = download_terraform_project_from_minio(user_id, project_name)
#         if not os.path.isdir(local_path):
#             return local_path  # error string

#         aws_access_key, aws_secret_key = get_aws_credentials_from_db(user_id)

#         terraform_env = os.environ.copy()
#         terraform_env["AWS_ACCESS_KEY_ID"] = aws_access_key
#         terraform_env["AWS_SECRET_ACCESS_KEY"] = aws_secret_key

#         print("🔧 Running terraform init...")
#         init_success, init_stdout, init_stderr = run_terraform_command(
#             ["terraform", "init", "-no-color"],
#             working_dir=local_path,
#             env=terraform_env
#         )
#         if not init_success:
#             return f"❌ Terraform init failed for `{project_name}`.\n\nSTDERR:\n{init_stderr}"

#         if action == "revert_back":
#             print("⏪ Reverting cloud infra to match current .tf file...")
#             success, stdout, stderr = run_terraform_command(
#                 ["terraform", "apply", "-auto-approve"],
#                 working_dir=local_path,
#                 env=terraform_env
#             )
#             print("📄 Terraform Apply STDOUT:\n", stdout)
#             print("📄 Terraform Apply STDERR:\n", stderr)
#             if success:
#                 return f"✅ Drift reverted successfully for project `{project_name}`.\n\nSTDOUT:\n{stdout}"
#             else:
#                 return f"❌ Terraform apply failed for project `{project_name}`.\n\nSTDERR:\n{stderr}"

#         elif action == "apply_drift":
#             with get_db_session() as db:
#                 drift_reason = fetch_drift_reason(db, user_id, project_name)
#                 if not drift_reason:
#                     return f"❌ No drift_reason found in DB for `{project_name}` (user {user_id})"

#             main_tf_path = os.path.join(local_path, "main.tf")
#             updated = update_tf_file_with_llm(main_tf_path, drift_reason)

#             if not updated:
#                 return f"❌ Failed to update main.tf for `{project_name}` using GPT."

#             print("📦 Applying updated main.tf with Terraform...")
#             success, stdout, stderr = run_terraform_command(
#                 ["terraform", "apply", "-auto-approve"],
#                 working_dir=local_path,
#                 env=terraform_env
#             )
#             print("📄 Terraform Apply STDOUT:\n", stdout)
#             print("📄 Terraform Apply STDERR:\n", stderr)
#             if success:
#                 upload_msg = upload_project_to_minio(local_path, user_id, project_name)
#                 return f"✅ Drift applied successfully for `{project_name}`.\n\n{upload_msg}\n\nSTDOUT:\n{stdout}"
#             else:
#                 return f"❌ Terraform apply failed after updating main.tf.\n\nSTDERR:\n{stderr}"

#         else:
#             return f"❌ Invalid action: `{action}`. Use either 'apply_drift' or 'revert_back'."

#     finally:
#         if local_path and os.path.isdir(local_path):
#             try:
#                 shutil.rmtree(local_path, ignore_errors=True)
#                 print(f"🧹 Cleaned up temp directory")
#             except Exception as cleanup_err:
#                 print(f"⚠️ Failed to clean temp folder: {cleanup_err}")


@tool
def drift_detection_tool(project_name: str, config: RunnableConfig, action: str):
    """
    This tool solves Terraform drift based on selected action:

    Args:
        project_name (str): Name of the Terraform project.
        config (RunnableConfig): Contains `user_id` inside config["configurable"].
        action (str): "apply_drift" to apply changes from drift, or "revert_back" to discard drift and apply original .tf file.

    Returns:
        str: Success or failure message.
    """
    user_id = config['configurable'].get('user_id', 'unknown')
    if user_id == 'unknown':
        return "❌ user_id not found in config['configurable']"

    print(f"✅ User ID extracted: {user_id} for project: {project_name}")

    local_path = None  # Define early for finally block

    try:
        local_path = download_terraform_project_from_minio(user_id, project_name)
        if not os.path.isdir(local_path):
            return local_path  # Contains error string if download failed

        aws_access_key, aws_secret_key = get_aws_credentials_from_db(user_id)

        terraform_env = os.environ.copy()
        terraform_env["AWS_ACCESS_KEY_ID"] = aws_access_key
        terraform_env["AWS_SECRET_ACCESS_KEY"] = aws_secret_key

        print("🔧 Running terraform init...")
        init_success, init_stdout, init_stderr = run_terraform_command(
            ["terraform", "init", "-no-color"],
            working_dir=local_path,
            env=terraform_env
        )
        if not init_success:
            return f"❌ Terraform init failed for `{project_name}`.\n\nSTDERR:\n{init_stderr}"

        if action == "revert_back":
            print("⏪ Reverting cloud infra to match current .tf file...")
            success, stdout, stderr = run_terraform_command(
                ["terraform", "apply", "-auto-approve"],
                working_dir=local_path,
                env=terraform_env
            )
            print("📄 Terraform Apply STDOUT:\n", stdout)
            print("📄 Terraform Apply STDERR:\n", stderr)

            if success:
                
                with get_db_session() as db:
                    print(f"🔄 Updating workspace status for '{project_name}' to 'synced'...")
                    status_data = WorkspaceStatusCreate(userid=user_id, project_name=project_name, status="synced")
                    create_or_update_workspace_status(db, status_data)
                    
                    print(f"🧹 Clearing resolved drift record for '{project_name}'...")
                    delete_drift_result(db, user_id, project_name)
                
                return f"✅ Drift reverted successfully for project `{project_name}`. Workspace is now synced and the drift record has been cleared.\n\nSTDOUT:\n{stdout}"
            else:
                return f"❌ Terraform apply failed for project `{project_name}`.\n\nSTDERR:\n{stderr}"

        elif action == "apply_drift":
            with get_db_session() as db:
                drift_reason = fetch_drift_reason(db, user_id, project_name)
                if not drift_reason:
                    return f"❌ No drift_reason found in DB for `{project_name}` (user {user_id})"

            main_tf_path = os.path.join(local_path, "main.tf")
            updated = update_tf_file_with_llm(main_tf_path, drift_reason)

            if not updated:
                return f"❌ Failed to update main.tf for `{project_name}` using GPT."

            print("📦 Applying updated main.tf with Terraform...")
            success, stdout, stderr = run_terraform_command(
                ["terraform", "apply", "-auto-approve"],
                working_dir=local_path,
                env=terraform_env
            )
            print("📄 Terraform Apply STDOUT:\n", stdout)
            print("📄 Terraform Apply STDERR:\n", stderr)

            if success:
                upload_msg = upload_project_to_minio(local_path, user_id, project_name)
                
                with get_db_session() as db:
                    print(f"🔄 Updating workspace status for '{project_name}' to 'synced'...")
                    status_data = WorkspaceStatusCreate(userid=user_id, project_name=project_name, status="synced")
                    create_or_update_workspace_status(db, status_data)

                    print(f"🧹 Clearing resolved drift record for '{project_name}'...")
                    delete_drift_result(db, user_id, project_name)
                
                return f"✅ Drift applied successfully for `{project_name}`. Workspace is now synced and the drift record has been cleared.\n\n{upload_msg}\n\nSTDOUT:\n{stdout}"
            else:
                return f"❌ Terraform apply failed after updating main.tf.\n\nSTDERR:\n{stderr}"

        else:
            return f"❌ Invalid action: `{action}`. Use either 'apply_drift' or 'revert_back'."

    finally:
        if local_path and os.path.isdir(local_path):
            try:
                shutil.rmtree(local_path, ignore_errors=True)
                print(f"🧹 Cleaned up temp directory")
            except Exception as cleanup_err:
                print(f"⚠️ Failed to clean temp folder: {cleanup_err}")