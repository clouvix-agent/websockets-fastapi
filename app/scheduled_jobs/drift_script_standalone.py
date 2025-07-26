import os
import subprocess
import sys
from datetime import datetime
from minio import Minio
from minio.error import S3Error
from sqlalchemy import text


import pytz

IST = pytz.timezone("Asia/Kolkata")

# ----------------------------------------
# ✅ CONFIGURATION (HARDCODED)
# ----------------------------------------
USER_ID = 3
ACCESS_KEY = ""
SECRET_KEY = ""

PROJECT_NAME = "srishti_test"  # 👈 Hardcoded project name
BUCKET_NAME = f"terraform-workspaces-user-{USER_ID}"
REMOTE_PATH = f"{PROJECT_NAME}_terraform"
LOCAL_BASE_DIR = os.path.abspath("temp_drift")
LOCAL_WORKSPACE_DIR = os.path.join(LOCAL_BASE_DIR, BUCKET_NAME, REMOTE_PATH)

# Terraform files
MAIN_TF_REMOTE = f"{REMOTE_PATH}/main.tf"
TFSTATE_REMOTE = f"{REMOTE_PATH}/terraform.tfstate"
MAIN_TF_LOCAL = os.path.join(LOCAL_WORKSPACE_DIR, "main.tf")
TFSTATE_LOCAL = os.path.join(LOCAL_WORKSPACE_DIR, "terraform.tfstate")

# MinIO Configuration
MINIO_CLIENT = Minio(
    "storage.clouvix.com",
    access_key="clouvix@gmail.com",
    secret_key="Clouvix@bangalore2025",
    secure=True
)

# Import your DB session
from app.database import get_db_session


# ----------------------------------------
# 🧰 UTILITY FUNCTIONS
# ----------------------------------------
def download_file(bucket: str, remote_key: str, local_path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        MINIO_CLIENT.fget_object(bucket, remote_key, local_path)
        print(f"📥 Downloaded: {remote_key} → {local_path}")
        return True
    except S3Error as e:
        print(f"❌ MinIO download failed for {remote_key}: {e}")
        return False


def run_terraform_command(command: list, working_dir: str, env: dict = None) -> subprocess.CompletedProcess:
    print(f"🛠️ Running: {' '.join(command)} in {working_dir}")
    try:
        return subprocess.run(
            command,
            cwd=working_dir,
            capture_output=True,
            text=True,
            check=False,
            env=env
        )
    except FileNotFoundError:
        print("❌ Terraform not found in PATH.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error running Terraform: {e}")
        sys.exit(1)


def detect_drift(terraform_dir: str, aws_key: str, aws_secret: str) -> str:
    if not os.path.isdir(terraform_dir):
        return f"ERROR: Directory not found → {terraform_dir}"

    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = aws_key
    env["AWS_SECRET_ACCESS_KEY"] = aws_secret

    plugin_cache = os.path.join(terraform_dir, ".terraform-plugin-cache")
    os.makedirs(plugin_cache, exist_ok=True)
    env["TF_PLUGIN_CACHE_DIR"] = plugin_cache

    # Terraform init
    init = run_terraform_command(
        ["terraform", "init", "-input=false", "-no-color", "-reconfigure"],
        terraform_dir,
        env
    )
    print(f"🛠️ Terraform init output: {init.stdout}")
    if init.returncode != 0:
        return f"INIT_FAILED\n{init.stderr}"

    # Terraform plan
    plan = run_terraform_command(
        ["terraform", "plan", "-no-color", "-detailed-exitcode"],
        terraform_dir,
        env
    )
    print(f"🛠️ Terraform plan output: {plan.stdout}")
    if plan.returncode == 0:
        return "NO_DRIFT\n" + plan.stdout
    elif plan.returncode == 2:
        return "DRIFT_DETECTED\n" + plan.stdout
    else:
        return f"PLAN_FAILED\n{plan.stderr}"


def save_drift_to_db(project_name: str, drift_reason: str):
    try:
        with get_db_session() as db:
            sql = text("""
                INSERT INTO drift_detection (userid, project_name, drift_reason, updated_time)
                VALUES (:u, :p, :r, :t)
                ON CONFLICT (userid, project_name)
                DO UPDATE SET
                    drift_reason = EXCLUDED.drift_reason,
                    updated_time = EXCLUDED.updated_time
            """)
            db.execute(sql, {
                "u": USER_ID,
                "p": project_name,
                "r": drift_reason,
                "t": datetime.now(IST)  # ⏰ Use IST time
            })
            db.commit()
            print(f"✅ Drift result saved (inserted or updated) for project: {project_name}")
    except Exception as e:
        print(f"❌ Failed to insert/update DB for {project_name}: {e}")


# ----------------------------------------
# 🚀 MAIN
# ----------------------------------------
def main():
    print(f"🚀 Drift detection started for project: {PROJECT_NAME}")
    print(f"📁 Local workspace: {LOCAL_WORKSPACE_DIR}")

    # Step 1: Download files from MinIO
    print("⬇️ Downloading Terraform files from MinIO...")
    if not download_file(BUCKET_NAME, MAIN_TF_REMOTE, MAIN_TF_LOCAL):
        return
    if not download_file(BUCKET_NAME, TFSTATE_REMOTE, TFSTATE_LOCAL):
        return

    # Step 2: Detect drift
    print("\n🔍 Running Terraform drift detection...")
    result = detect_drift(LOCAL_WORKSPACE_DIR, ACCESS_KEY, SECRET_KEY)

    if result.startswith("DRIFT_DETECTED"):
        drift_reason = result.split("DRIFT_DETECTED\n", 1)[1]
        save_drift_to_db(PROJECT_NAME, drift_reason)
    elif result.startswith("NO_DRIFT"):
        print("✅ No drift detected.")
    else:
        print(f"⚠️ Terraform error:\n{result}")


# ----------------------------------------
# 🟢 ENTRY POINT
# ----------------------------------------
if __name__ == "__main__":
    main()

