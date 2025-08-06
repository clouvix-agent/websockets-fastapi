# import os
# import json
# import subprocess
# import sys
# import concurrent.futures
# import threading
# import shutil
# from typing import List, Dict, Tuple
# from collections import defaultdict

# # It's good practice to handle potential import errors
# try:
#     from minio import Minio
#     from minio.error import S3Error
#     import boto3
#     from botocore.exceptions import ClientError
# except ImportError as e:
#     print(f"❌ Missing required library: {e}. Please run 'pip install minio boto3'.")
#     sys.exit(1)

# # Assuming these are your application's modules
# from app.database import get_db_session
# from app.models.workspace import Workspace
# from app.db.connection import get_user_connections_by_type
# from app.db.drift import save_drift_result
# from app.db.workspace_status import create_or_update_workspace_status
# from app.schemas.workspace_status import WorkspaceStatusCreate


# # ========================
# # Configuration
# # ========================
# MINIO_ENDPOINT = "storage.clouvix.com"
# MINIO_ACCESS_KEY = "clouvix@gmail.com"
# MINIO_SECRET_KEY = "Clouvix@bangalore2025"
# MINIO_SECURE = True
# MAX_WORKERS = 8  # Number of parallel Terraform executions

# # Initialize MinIO client
# minio_client = Minio(
#     MINIO_ENDPOINT,
#     access_key=MINIO_ACCESS_KEY,
#     secret_key=MINIO_SECRET_KEY,
#     secure=MINIO_SECURE
# )

# # --- Paths for temporary files and final reports ---
# TEMP_DRIFT_DIR = os.path.abspath("temp_drift")
# REPORT_DIR = os.path.abspath("drift_reports")
# SKIPPED_FILE = os.path.join(REPORT_DIR, "skipped_projects.txt")
# DRIFT_FILE = os.path.join(REPORT_DIR, "drift_detected.txt")
# NO_DRIFT_FILE = os.path.join(REPORT_DIR, "no_drift_detected.txt")


# # --- Thread-safe lists for reporting ---
# skipped_list = []
# drift_list = []
# no_drift_list = []
# # A lock is crucial to prevent race conditions when threads append to the lists
# list_lock = threading.Lock()


# # ------------------------------------
# # 🧰 UTILITY & VALIDATION FUNCTIONS
# # ------------------------------------

# def normalize_object_path(path: str) -> str:
#     """Standardizes object storage paths."""
#     return path.replace("\\", "/").strip("/")

# def are_aws_credentials_valid(aws_key: str, aws_secret: str) -> bool:
#     """
#     Validates AWS credentials by making a simple API call.
#     """
#     try:
#         sts_client = boto3.client(
#             'sts',
#             aws_access_key_id=aws_key,
#             aws_secret_access_key=aws_secret,
#             region_name='us-east-1'
#         )
#         sts_client.get_caller_identity()
#         print("✅ AWS credentials are valid.")
#         return True
#     except ClientError as e:
#         if e.response['Error']['Code'] == 'InvalidClientTokenId':
#             print("❌ AWS credentials are NOT valid.")
#         else:
#             print(f"❌ An unexpected AWS error occurred: {e}")
#         return False
#     except Exception as e:
#         print(f"❌ A non-AWS error occurred during credential validation: {e}")
#         return False

# def get_aws_credentials_from_db(user_id: int) -> Tuple[str, str]:
#     """Fetches AWS credentials from the database for a given user."""
#     print(f"🔑 Fetching AWS credentials for user {user_id}")
#     with get_db_session() as db:
#         connections = get_user_connections_by_type(db, user_id, "aws")
#         if not connections:
#             raise ValueError(f"No AWS connection found for user {user_id}")

#         connection = connections[0]
#         connection_data = json.loads(connection.connection_json)

#         aws_access_key = next((item["value"] for item in connection_data if item["key"] == "AWS_ACCESS_KEY_ID"), None)
#         aws_secret_key = next((item["value"] for item in connection_data if item["key"] == "AWS_SECRET_ACCESS_KEY"), None)

#         if not aws_access_key or not aws_secret_key:
#             raise ValueError(f"AWS credentials are incomplete for user {user_id}")

#         return aws_access_key, aws_secret_key

# def object_exists(bucket_name: str, object_path: str) -> bool:
#     """Checks if an object exists in a MinIO bucket."""
#     try:
#         minio_client.stat_object(bucket_name, object_path)
#         return True
#     except S3Error:
#         return False

# def download_file_from_minio(bucket: str, object_path: str, local_path: str) -> bool:
#     """Downloads a file from MinIO to a local path."""
#     try:
#         os.makedirs(os.path.dirname(local_path), exist_ok=True)
#         minio_client.fget_object(bucket, object_path, local_path)
#         print(f"📥 Downloaded {object_path} to {local_path}")
#         return True
#     except S3Error as e:
#         print(f"❌ Failed to fetch '{object_path}' from MinIO: {e}")
#         return False

# # ------------------------------------
# # ⚙️ TERRAFORM DRIFT DETECTION
# # ------------------------------------

# def run_terraform_command(command: list, working_dir: str, env: dict = None) -> subprocess.CompletedProcess:
#     """Executes a Terraform command and captures its output."""
#     print(f"🚀 Running: {' '.join(command)} in {working_dir}...")
#     try:
#         return subprocess.run(
#             command,
#             cwd=working_dir,
#             capture_output=True,
#             text=True,
#             check=False,
#             env=env
#         )
#     except FileNotFoundError:
#         print("❌ Terraform not found. Ensure it is installed and in your system's PATH.", file=sys.stderr)
#         # In a scheduled job, we should not exit the whole application
#         # Instead, we return a failed process object that can be handled by the caller
#         return subprocess.CompletedProcess(command, 1, stdout="", stderr="Terraform executable not found.")
#     except Exception as e:
#         print(f"❌ An unexpected error occurred while running Terraform: {e}", file=sys.stderr)
#         return subprocess.CompletedProcess(command, 1, stdout="", stderr=str(e))


# def detect_terraform_drift(terraform_working_dir: str, aws_key: str, aws_secret: str) -> str:
#     """Runs terraform init and plan to detect infrastructure drift."""
#     if not os.path.isdir(terraform_working_dir):
#         return f"Error: Invalid directory: '{terraform_working_dir}'"

#     terraform_env = os.environ.copy()
#     terraform_env["AWS_ACCESS_KEY_ID"] = aws_key
#     terraform_env["AWS_SECRET_ACCESS_KEY"] = aws_secret
    
#     plugin_cache_dir = os.path.join(terraform_working_dir, ".terraform-plugin-cache")
#     os.makedirs(plugin_cache_dir, exist_ok=True)
#     terraform_env["TF_PLUGIN_CACHE_DIR"] = plugin_cache_dir
#     print(f"   -> Using isolated plugin cache: {plugin_cache_dir}")

#     init_command = ["terraform", "init", "-input=false", "-no-color", "-reconfigure"]
#     init_result = run_terraform_command(init_command, terraform_working_dir, terraform_env)
#     if init_result.returncode != 0:
#         return f"Terraform Init Failed:\n{init_result.stderr}"
#     print(f"✅ Terraform Init successful for {os.path.basename(terraform_working_dir)}.")

#     plan_command = ["terraform", "plan", "-no-color", "-detailed-exitcode"]
#     plan_result = run_terraform_command(plan_command, terraform_working_dir, terraform_env)
    
#     full_output = f"STDOUT:\n{plan_result.stdout}\n\nSTDERR:\n{plan_result.stderr}"
    
#     if plan_result.returncode == 0:
#         return f"NO_DRIFT_DETECTED\n{full_output}"
#     elif plan_result.returncode == 2:
#         return f"DRIFT_DETECTED\n{full_output}"
#     else:
#         return f"TERRAFORM_PLAN_FAILED\n{full_output}"


# # ------------------------------------
# # 📦 DATA COLLECTION & WORKER FUNCTION
# # ------------------------------------

# def collect_workspace_execution_data() -> List[Dict]:
#     """Gathers all necessary data for each workspace from the database and MinIO."""
#     print("📦 Collecting and preparing workspace execution data...")
#     collected_data = []
#     workspaces_by_user: Dict[int, List[Workspace]] = defaultdict(list)

#     with get_db_session() as db:
#         all_workspaces = db.query(Workspace).all()
#         for ws in all_workspaces:
#             workspaces_by_user[ws.userid].append(ws)

#     for user_id, user_workspaces in workspaces_by_user.items():
#         if user_id == 7:
#             print(f"⏭️ Skipping user {user_id} (test customer)")
#             continue

#         try:
#             aws_access_key, aws_secret_key = get_aws_credentials_from_db(user_id)
#         except Exception as e:
#             reason = f"Could not fetch credentials: {e}"
#             for ws in user_workspaces:
#                 with list_lock:
#                     skipped_list.append(f"Workspace: {ws.wsname} (ID: {ws.wsid}, User: {user_id}) - Reason: {reason}")
#             continue

#         for ws in user_workspaces:
#             if not ws.filelocation:
#                 reason = "Missing 'filelocation' in database"
#                 with list_lock:
#                     skipped_list.append(f"Workspace: {ws.wsname} (ID: {ws.wsid}, User: {user_id}) - Reason: {reason}")
#                 continue

#             bucket = f"terraform-workspaces-user-{user_id}"
#             normalized_location = normalize_object_path(ws.filelocation)
#             terraform_dir = os.path.dirname(normalized_location) if normalized_location.endswith("/main.tf") else normalized_location
            
#             tfstate_key = f"{terraform_dir}/terraform.tfstate"
#             main_tf_key = f"{terraform_dir}/main.tf"
#             base_path = os.path.join(TEMP_DRIFT_DIR, bucket, terraform_dir)

#             if not object_exists(bucket, tfstate_key):
#                 reason = f"terraform.tfstate not found in {bucket}/{tfstate_key}"
#                 with list_lock:
#                     skipped_list.append(f"Workspace: {ws.wsname} (ID: {ws.wsid}, User: {user_id}) - Reason: {reason}")
#                 continue

#             main_tf_downloaded = download_file_from_minio(bucket, main_tf_key, os.path.join(base_path, "main.tf"))
#             tfstate_downloaded = download_file_from_minio(bucket, tfstate_key, os.path.join(base_path, "terraform.tfstate"))

#             if not (main_tf_downloaded and tfstate_downloaded):
#                 reason = "Failed to download necessary Terraform files from MinIO"
#                 with list_lock:
#                     skipped_list.append(f"Workspace: {ws.wsname} (ID: {ws.wsid}, User: {user_id}) - Reason: {reason}")
#                 continue

#             collected_data.append({
#                 "user_id": user_id, "workspace_id": ws.wsid, "workspace_name": ws.wsname,
#                 "terraform_dir": base_path, "aws_key": aws_access_key, "aws_secret": aws_secret_key
#             })
#     return collected_data


# def run_drift_check_for_workspace(workspace: Dict):
#     """
#     Worker function executed by each thread. Validates credentials, runs Terraform,
#     and records the result.
#     """
#     ws_name = workspace['workspace_name']
#     user_id = workspace['user_id']
#     ws_identifier = f"Workspace: {ws_name} (ID: {workspace['workspace_id']}, User: {user_id})"

#     print(f"🕵️  Validating credentials for {ws_identifier}")
#     if not are_aws_credentials_valid(workspace["aws_key"], workspace["aws_secret"]):
#         with list_lock:
#             skipped_list.append(f"{ws_identifier} - Reason: Invalid AWS credentials.")
#         return

#     print(f"🔧 Starting Terraform drift check for: {ws_identifier}")
#     result = detect_terraform_drift(
#         terraform_working_dir=workspace["terraform_dir"],
#         aws_key=workspace["aws_key"],
#         aws_secret=workspace["aws_secret"]
#     )

#     if result.startswith("DRIFT_DETECTED"):
#         drift_reason = result.replace("DRIFT_DETECTED\n", "", 1)
#         print(f"⚠️ Drift DETECTED for {ws_name}.")
#         with list_lock:
#             drift_list.append(ws_identifier)
#         try:
#             with get_db_session() as db:
#                 # Save the drift reason
#                 save_drift_result(
#                     db=db, userid=user_id, project_name=ws_name, drift_reason=drift_reason
#                 )
#                 # Update the workspace status to 'drifted'
#                 status_data = WorkspaceStatusCreate(userid=user_id, project_name=ws_name, status="drifted")
#                 create_or_update_workspace_status(db, status_data)
#             print(f"💾 Drift result and status saved to DB for {ws_name}")
#         except Exception as e:
#             print(f"❌ Failed to save drift result to DB for {ws_name}: {e}")
            
#     elif result.startswith("NO_DRIFT_DETECTED"):
#         print(f"✅ No drift detected for {ws_name}.")
#         with list_lock:
#             no_drift_list.append(ws_identifier)
            
#     else: # Handle Terraform Init or Plan failures
#         with list_lock:
#             skipped_list.append(f"{ws_identifier} - Reason: Terraform execution error.\n--- Output ---\n{result}\n--------------")


# # ------------------------------------
# # 🚀 MAIN SCHEDULABLE JOB
# # ------------------------------------

# def run_daily_drift_detection_job():
#     """
#     The main function to be called by the scheduler.
#     It orchestrates the entire drift detection process.
#     """
#     print("\n" + "="*80)
#     print("🌅 STARTING DAILY DRIFT DETECTION JOB")
#     print("="*80)
    
#     # Clear lists from previous runs
#     global skipped_list, drift_list, no_drift_list
#     skipped_list, drift_list, no_drift_list = [], [], []

#     # Ensure report directory exists
#     os.makedirs(REPORT_DIR, exist_ok=True)
#     print(f"📝 Reports will be saved in: {REPORT_DIR}")

#     # Clean up old temporary files if they exist
#     if os.path.exists(TEMP_DRIFT_DIR):
#         shutil.rmtree(TEMP_DRIFT_DIR)
#     os.makedirs(TEMP_DRIFT_DIR)

#     # --- Step 1: Collect data ---
#     workspaces_to_process = collect_workspace_execution_data()

#     if not workspaces_to_process:
#         print("\nNo valid workspaces found to process.")
#     else:
#         # --- Step 2: Run checks in parallel ---
#         print(f"\n🔎 Submitting {len(workspaces_to_process)} workspaces for parallel drift detection (max_workers={MAX_WORKERS})...")
#         with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
#             futures = [executor.submit(run_drift_check_for_workspace, ws) for ws in workspaces_to_process]
#             for future in concurrent.futures.as_completed(futures):
#                 try:
#                     future.result()
#                 except Exception as exc:
#                     print(f"❌ A critical error occurred in a worker thread: {exc}")

#     # --- Step 3: Write report files ---
#     print("\n\n" + "="*80)
#     print("📊 Generating Final Reports...")
#     print("="*80)

#     try:
#         with open(SKIPPED_FILE, 'w') as f:
#             f.write("--- Skipped Workspaces ---\n\n")
#             f.write("\n\n".join(skipped_list) if skipped_list else "No workspaces were skipped.")
#         print(f"📄 Saved skipped projects report to: {SKIPPED_FILE}")

#         with open(DRIFT_FILE, 'w') as f:
#             f.write("--- Workspaces with Detected Drift ---\n\n")
#             f.write("\n".join(drift_list) if drift_list else "No drift was detected in any workspace.")
#         print(f"📄 Saved drift detected report to: {DRIFT_FILE}")

#         with open(NO_DRIFT_FILE, 'w') as f:
#             f.write("--- Workspaces with No Drift ---\n\n")
#             f.write("\n".join(no_drift_list) if no_drift_list else "No workspaces were confirmed to be up-to-date.")
#         print(f"📄 Saved no-drift report to: {NO_DRIFT_FILE}")

#     except IOError as e:
#         print(f"❌ Error writing report files: {e}")

#     print("\n🎉 All drift detection tasks complete.")
#     print("="*80 + "\n")

import os
import json
import subprocess
import sys
import concurrent.futures
import threading
import shutil
from typing import List, Dict, Tuple
from collections import defaultdict

try:
    from minio import Minio
    from minio.error import S3Error
    import boto3
    from botocore.exceptions import ClientError
except ImportError as e:
    print(f"❌ Missing library: {e}. Run 'pip install minio boto3'")
    sys.exit(1)

from app.database import get_db_session
from app.models.workspace import Workspace
from app.db.connection import get_user_connections_by_type
from app.db.drift import save_drift_result
from app.db.workspace_status import create_or_update_workspace_status
from app.schemas.workspace_status import WorkspaceStatusCreate

MINIO_ENDPOINT = "storage.clouvix.com"
MINIO_ACCESS_KEY = "clouvix@gmail.com"
MINIO_SECRET_KEY = "Clouvix@bangalore2025"
MINIO_SECURE = True
MAX_WORKERS = 8

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

TEMP_DRIFT_DIR = os.path.abspath("temp_drift")
REPORT_DIR = os.path.abspath("drift_reports")
SKIPPED_FILE = os.path.join(REPORT_DIR, "skipped_projects.txt")
DRIFT_FILE = os.path.join(REPORT_DIR, "drift_detected.txt")
NO_DRIFT_FILE = os.path.join(REPORT_DIR, "no_drift_detected.txt")

skipped_list = []
drift_list = []
no_drift_list = []
list_lock = threading.Lock()

def normalize_object_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")

def are_aws_credentials_valid(aws_key: str, aws_secret: str) -> bool:
    try:
        sts_client = boto3.client(
            'sts',
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
            region_name='us-east-1'
        )
        sts_client.get_caller_identity()
        return True
    except Exception:
        return False

def get_aws_credentials_from_db(user_id: int) -> Tuple[str, str]:
    with get_db_session() as db:
        connections = get_user_connections_by_type(db, user_id, "aws")
        if not connections:
            raise ValueError(f"No AWS connection found for user {user_id}")
        connection_data = json.loads(connections[0].connection_json)
        aws_access_key = next((x["value"] for x in connection_data if x["key"] == "AWS_ACCESS_KEY_ID"), None)
        aws_secret_key = next((x["value"] for x in connection_data if x["key"] == "AWS_SECRET_ACCESS_KEY"), None)
        return aws_access_key, aws_secret_key

def object_exists(bucket_name: str, object_path: str) -> bool:
    try:
        minio_client.stat_object(bucket_name, object_path)
        return True
    except S3Error:
        return False

def download_file_from_minio(bucket: str, object_path: str, local_path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        minio_client.fget_object(bucket, object_path, local_path)
        return True
    except S3Error:
        return False

def run_terraform_command(command: list, working_dir: str, env: dict = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=working_dir,
        capture_output=True,
        text=True,
        check=False,
        env=env
    )

def detect_terraform_drift(terraform_working_dir: str, aws_key: str, aws_secret: str) -> str:
    if not os.path.isdir(terraform_working_dir):
        return f"Invalid dir: {terraform_working_dir}"

    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = aws_key
    env["AWS_SECRET_ACCESS_KEY"] = aws_secret
    env["TF_PLUGIN_CACHE_DIR"] = os.path.join(terraform_working_dir, ".terraform-plugin-cache")
    os.makedirs(env["TF_PLUGIN_CACHE_DIR"], exist_ok=True)

    # Inject AWS credentials into provider.tf
    provider_tf_path = None
    original_content = None
    for root, _, files in os.walk(terraform_working_dir):
        for file in files:
            if file == "provider.tf":
                provider_tf_path = os.path.join(root, file)
                break

    if not provider_tf_path:
        return "Error: provider.tf not found"

    with open(provider_tf_path, "r") as f:
        original_content = f.read()

    injected = []
    inside_provider = False
    for line in original_content.splitlines():
        if line.strip().startswith('provider "aws"'):
            inside_provider = True
        elif inside_provider and line.strip().startswith("}"):
            injected.append(f'  access_key = "{aws_key}"')
            injected.append(f'  secret_key = "{aws_secret}"')
            inside_provider = False
        injected.append(line)

    with open(provider_tf_path, "w") as f:
        f.write("\n".join(injected))

    try:
        init = run_terraform_command(["terraform", "init", "-input=false", "-no-color", "-reconfigure"], terraform_working_dir, env)
        if init.returncode != 0:
            return f"Init failed:\n{init.stderr}"

        plan = run_terraform_command(["terraform", "plan", "-no-color", "-detailed-exitcode"], terraform_working_dir, env)
        if plan.returncode == 0:
            return "NO_DRIFT_DETECTED\n" + plan.stdout
        elif plan.returncode == 2:
            return "DRIFT_DETECTED\n" + plan.stdout
        else:
            return "PLAN_FAILED\n" + plan.stderr
    finally:
        if provider_tf_path and original_content:
            with open(provider_tf_path, "w") as f:
                f.write(original_content)

def collect_workspace_execution_data() -> List[Dict]:
    print("📦 Collecting workspace execution data...")
    collected_data = []
    workspaces_by_user: Dict[int, List[Workspace]] = defaultdict(list)

    with get_db_session() as db:
        all_workspaces = db.query(Workspace).all()
        for ws in all_workspaces:
            workspaces_by_user[ws.userid].append(ws)

    for user_id, user_workspaces in workspaces_by_user.items():
        if user_id == 7:
            print(f"⏭️ Skipping test user {user_id}")
            continue

        try:
            aws_key, aws_secret = get_aws_credentials_from_db(user_id)
        except Exception as e:
            for ws in user_workspaces:
                with list_lock:
                    skipped_list.append(f"{ws.wsname} (User {user_id}) - Reason: Credential fetch failed: {e}")
            continue

        for ws in user_workspaces:
            if not ws.filelocation:
                with list_lock:
                    skipped_list.append(f"{ws.wsname} (User {user_id}) - Reason: Missing filelocation")
                continue

            bucket = f"terraform-workspaces-user-{user_id}"
            path = normalize_object_path(ws.filelocation)
            tf_dir = os.path.dirname(path) if path.endswith("/main.tf") else path
            local_dir = os.path.join(TEMP_DRIFT_DIR, bucket, tf_dir)

            tfstate_key = f"{tf_dir}/terraform.tfstate"
            if not object_exists(bucket, tfstate_key):
                with list_lock:
                    skipped_list.append(f"{ws.wsname} - Reason: Missing terraform.tfstate")
                continue

            # Download all .tf files
            tf_downloaded = False
            try:
                for obj in minio_client.list_objects(bucket, prefix=tf_dir + "/", recursive=True):
                    if obj.object_name.endswith(".tf"):
                        local_path = os.path.join(local_dir, os.path.relpath(obj.object_name, tf_dir))
                        if download_file_from_minio(bucket, obj.object_name, local_path):
                            tf_downloaded = True
            except Exception as e:
                with list_lock:
                    skipped_list.append(f"{ws.wsname} - Error downloading .tf files: {e}")
                continue

            if not tf_downloaded:
                with list_lock:
                    skipped_list.append(f"{ws.wsname} - No .tf files downloaded.")
                continue

            # Download terraform.tfstate
            download_file_from_minio(bucket, tfstate_key, os.path.join(local_dir, "terraform.tfstate"))

            collected_data.append({
                "user_id": user_id,
                "workspace_id": ws.wsid,
                "workspace_name": ws.wsname,
                "terraform_dir": local_dir,
                "aws_key": aws_key,
                "aws_secret": aws_secret
            })

    return collected_data

def run_drift_check_for_workspace(workspace: Dict):
    ws_name = workspace['workspace_name']
    user_id = workspace['user_id']
    ws_id = workspace['workspace_id']
    label = f"{ws_name} (ID {ws_id}, User {user_id})"

    print(f"🔎 Running drift check: {label}")

    if not are_aws_credentials_valid(workspace["aws_key"], workspace["aws_secret"]):
        with list_lock:
            skipped_list.append(f"{label} - Invalid AWS credentials")
        return

    result = detect_terraform_drift(
        terraform_working_dir=workspace["terraform_dir"],
        aws_key=workspace["aws_key"],
        aws_secret=workspace["aws_secret"]
    )

    if result.startswith("DRIFT_DETECTED"):
        drift_reason = result.replace("DRIFT_DETECTED\n", "", 1)
        print(f"⚠️ Drift detected for {label}")
        with list_lock:
            drift_list.append(label)
        try:
            with get_db_session() as db:
                save_drift_result(db=db, userid=user_id, project_name=ws_name, drift_reason=drift_reason)
                status_data = WorkspaceStatusCreate(userid=user_id, project_name=ws_name, status="drifted")
                create_or_update_workspace_status(db, status_data)
            print(f"✅ Drift saved for {label}")
        except Exception as e:
            print(f"❌ DB error for {label}: {e}")
    elif result.startswith("NO_DRIFT_DETECTED"):
        print(f"✅ No drift for {label}")
        with list_lock:
            no_drift_list.append(label)
    else:
        print(f"❌ Error during Terraform for {label}")
        with list_lock:
            skipped_list.append(f"{label} - Terraform error:\n{result}")

def run_daily_drift_detection_job():
    print("=" * 80)
    print("🕒 STARTING DAILY DRIFT DETECTION")
    print("=" * 80)

    global skipped_list, drift_list, no_drift_list
    skipped_list, drift_list, no_drift_list = [], [], []

    os.makedirs(REPORT_DIR, exist_ok=True)
    if os.path.exists(TEMP_DRIFT_DIR):
        shutil.rmtree(TEMP_DRIFT_DIR)
    os.makedirs(TEMP_DRIFT_DIR)

    workspaces = collect_workspace_execution_data()

    if not workspaces:
        print("❗ No workspaces to process.")
        return

    print(f"🚀 Executing drift checks for {len(workspaces)} workspaces (max_workers={MAX_WORKERS})")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(run_drift_check_for_workspace, ws) for ws in workspaces]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                print(f"❌ Error in thread: {exc}")

    print("=" * 80)
    print("📊 Drift Detection Report Summary")
    print("=" * 80)

    try:
        with open(SKIPPED_FILE, 'w') as f:
            f.write("--- Skipped ---\n\n" + ("\n".join(skipped_list) if skipped_list else "None"))

        with open(DRIFT_FILE, 'w') as f:
            f.write("--- Drift Detected ---\n\n" + ("\n".join(drift_list) if drift_list else "None"))

        with open(NO_DRIFT_FILE, 'w') as f:
            f.write("--- No Drift ---\n\n" + ("\n".join(no_drift_list) if no_drift_list else "None"))

        print(f"📄 Reports saved to {REPORT_DIR}")
    except Exception as e:
        print(f"❌ Failed to write report files: {e}")

    print("✅ Drift detection complete.\n")
