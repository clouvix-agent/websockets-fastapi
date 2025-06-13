from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from minio import Minio
from minio.error import S3Error
import os, tempfile, shutil, subprocess, json

from app.database import get_db
from app.auth.utils import SECRET_KEY, ALGORITHM
# from app.models.connection import get_user_connections_by_type

router = APIRouter(
    prefix="/api/terraform",
    tags=["terraform"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_user_id(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("id")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

# --- READ Terraform Files ---
@router.get("/read")
async def read_terraform_files(
    project_name: str = Query(...),
    token: str = Depends(oauth2_scheme)
):
    user_id = get_user_id(token)
    bucket_name = f"terraform-workspaces-user-{user_id}"
    folder_name = f"{project_name}_terraform"

    temp_dir = tempfile.mkdtemp()
    download_path = os.path.join(temp_dir, folder_name)
    os.makedirs(download_path, exist_ok=True)

    try:
        minio_client = Minio(
            "storage.clouvix.com",
            access_key="clouvix@gmail.com",
            secret_key="Clouvix@bangalore2025",
            secure=True
        )

        files_found = False
        for obj in minio_client.list_objects(bucket_name, prefix=f"{folder_name}/", recursive=True):
            object_key = obj.object_name
            relative_path = object_key[len(folder_name) + 1:]
            local_path = os.path.join(download_path, relative_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            minio_client.fget_object(bucket_name, object_key, local_path)
            files_found = True

        if not files_found:
            raise HTTPException(status_code=404, detail="No files found in the Terraform project.")

        output = f"# 📁 Contents of `{project_name}_terraform`:\n"
        for root, _, files in os.walk(download_path):
            for filename in files:
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, download_path)
                try:
                    with open(filepath, "r") as f:
                        content = f.read()
                except Exception as e:
                    content = f"⚠️ Could not read file: {e}"

                output += f"\n## 📄 `{rel_path}`\n```hcl\n{content.strip()}\n```\n"

        return {
            "status": "success",
            "markdown": output
        }

    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"MinIO error: {str(e)}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# --- DESTROY Terraform ---
# @router.post("/destroy")
# async def destroy_terraform_project(
#     project_name: str = Query(...),
#     token: str = Depends(oauth2_scheme),
#     db: Session = Depends(get_db)
# ):
#     user_id = get_user_id(token)
#     bucket_name = f"terraform-workspaces-user-{user_id}"
#     folder_name = f"{project_name}_terraform"

#     temp_dir = tempfile.mkdtemp()
#     local_tf_dir = os.path.join(temp_dir, folder_name)
#     os.makedirs(local_tf_dir, exist_ok=True)

#     try:
#         minio_client = Minio(
#             "storage.clouvix.com",
#             access_key="clouvix@gmail.com",
#             secret_key="Clouvix@bangalore2025",
#             secure=True
#         )

#         for obj in minio_client.list_objects(bucket_name, prefix=f"{folder_name}/", recursive=True):
#             object_key = obj.object_name
#             relative_path = object_key[len(folder_name) + 1:]
#             local_path = os.path.join(local_tf_dir, relative_path)
#             os.makedirs(os.path.dirname(local_path), exist_ok=True)
#             minio_client.fget_object(bucket_name, object_key, local_path)

#         terraform_file_path = os.path.join(local_tf_dir, "main.tf")
#         if not os.path.exists(terraform_file_path):
#             raise HTTPException(status_code=404, detail="main.tf not found in project.")

#         # Get AWS creds
#         connections = get_user_connections_by_type(db, user_id, "aws")
#         if not connections:
#             raise HTTPException(status_code=400, detail="No AWS connection found for user.")
#         connection_data = json.loads(connections[0].connection_json)
#         aws_access_key = next((item["value"] for item in connection_data if item["key"] == "AWS_ACCESS_KEY_ID"), None)
#         aws_secret_key = next((item["value"] for item in connection_data if item["key"] == "AWS_SECRET_ACCESS_KEY"), None)

#         if not aws_access_key or not aws_secret_key:
#             raise HTTPException(status_code=400, detail="AWS credentials incomplete.")

#         env = os.environ.copy()
#         env["AWS_ACCESS_KEY_ID"] = aws_access_key
#         env["AWS_SECRET_ACCESS_KEY"] = aws_secret_key

#         subprocess.run(["terraform", "init"], cwd=local_tf_dir, check=True, env=env)

#         result = subprocess.run(
#             ["terraform", "destroy", "-auto-approve"],
#             cwd=local_tf_dir,
#             capture_output=True,
#             text=True,
#             env=env
#         )

#         if result.returncode == 0:
#             return {
#                 "status": "success",
#                 "output": result.stdout.strip()
#             }
#         else:
#             return {
#                 "status": "failure",
#                 "error": result.stderr.strip()
#             }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Terraform destroy failed: {str(e)}")
#     finally:
#         shutil.rmtree(temp_dir, ignore_errors=True)
