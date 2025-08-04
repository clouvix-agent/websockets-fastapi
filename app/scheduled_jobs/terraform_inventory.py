from sqlalchemy.orm import Session
from app.database import get_db_session
from app.models.user import User
from app.models.infrastructure_inventory import InfrastructureInventory
from minio import Minio
from minio.error import S3Error
import os
import tempfile
import shutil
import json
from datetime import datetime


def map_terraform_type(terraform_type):
    mapping = {
        "aws_instance": "EC2",
        "aws_s3_bucket": "S3",
        "aws_db_instance": "RDS",
        "aws_iam_policy": "IAM Policy",
        "aws_iam_role": "IAM Role",
        "aws_cloudwatch_log_group": "CloudWatch Log Group",
        "aws_internet_gateway": "Internet Gateway",
        # Add more mappings as needed
    }
    return mapping.get(terraform_type, terraform_type)


def fetch_all_state_files():
    minio_client = Minio(
        "storage.clouvix.com",
        access_key="clouvix@gmail.com",
        secret_key="Clouvix@bangalore2025",
        secure=True
    )

    with get_db_session() as db:
        user_ids = (
            db.query(User.id)
            .distinct()
            .all()
        )
        user_ids = [uid[0] for uid in user_ids]

        print(f"🔎 Found {len(user_ids)} users to process.")

        for user_id in user_ids:
            bucket_name = f"terraform-workspaces-user-{user_id}"
            print(f"📦 Checking bucket: {bucket_name}")

            try:
                objects = minio_client.list_objects(bucket_name, recursive=True)
                project_folders = set()

                for obj in objects:
                    if '/' in obj.object_name:
                        folder = obj.object_name.split('/')[0]
                        project_folders.add(folder)

                print(f"📂 Found project folders: {project_folders}")

                for folder in project_folders:
                    project_name = folder.replace("_terraform", "")
                    state_key = f"{folder}/terraform.tfstate"
                    try:
                        temp_dir = tempfile.mkdtemp()
                        local_state_file = os.path.join(temp_dir, "terraform.tfstate")

                        minio_client.fget_object(bucket_name, state_key, local_state_file)

                        with open(local_state_file, "r") as f:
                            state_data = json.load(f)

                        print(f"✅ Collected state for user {user_id}, project {project_name}")

                        # Track ARNs in this state file (for cleanup later)
                        current_arns = []

                        # Process each resource
                        for resource in state_data.get("resources", []):
                            terraform_type = resource.get("type")
                            resource_name = resource.get("name")
                            instances = resource.get("instances", [])

                            for instance in instances:
                                attributes = instance.get("attributes", {})
                                arn = attributes.get("arn")
                                resource_identifier = (
                                    attributes.get("id") or
                                    attributes.get("name") or
                                    attributes.get("bucket") or
                                    ""
                                )

                                if not arn:
                                    print(f"⚠️ Skipping resource {resource_name} (no ARN)")
                                    continue

                                resource_type = map_terraform_type(terraform_type)
                                current_arns.append(arn)

                                # Check if this resource already exists
                                existing_entry = db.query(InfrastructureInventory).filter_by(
                                    user_id=user_id,
                                    project_name=project_name,
                                    arn=arn
                                ).first()

                                if existing_entry:
                                    # Update existing
                                    existing_entry.resource_type = resource_type
                                    existing_entry.resource_name = resource_name
                                    existing_entry.terraform_type = terraform_type
                                    existing_entry.resource_identifier = resource_identifier
                                    existing_entry.attributes = attributes
                                    existing_entry.dependencies = instance.get("dependencies", [])
                                    existing_entry.updated_at = datetime.utcnow()
                                    print(f"🔄 Updated {resource_type} {arn}")
                                else:
                                    # New insert
                                    new_entry = InfrastructureInventory(
                                        user_id=user_id,
                                        project_name=project_name,
                                        resource_type=resource_type,
                                        resource_name=resource_name,
                                        arn=arn,
                                        terraform_type=terraform_type,
                                        resource_identifier=resource_identifier,
                                        attributes=attributes,
                                        dependencies=instance.get("dependencies", []),
                                        created_at=datetime.utcnow(),
                                        updated_at=datetime.utcnow()
                                    )
                                    db.add(new_entry)
                                    print(f"➕ Added {resource_type} {arn}")

                        # ✅ Cleanup: Remove resources no longer in the state
                        existing_resources = db.query(InfrastructureInventory).filter_by(
                            user_id=user_id,
                            project_name=project_name
                        ).all()

                        for res in existing_resources:
                            if res.arn not in current_arns:
                                print(f"❌ Removing resource no longer in state: {res.arn}")
                                db.delete(res)

                        db.commit()

                    except S3Error as e:
                        print(f"⚠️ No state file for {project_name} ({user_id}): {str(e)}")
                    finally:
                        shutil.rmtree(temp_dir, ignore_errors=True)

            except S3Error as e:
                print(f"❌ Could not access bucket {bucket_name}: {str(e)}")

    print(f"✅ Inventory sync complete at {datetime.utcnow()}")

# # --- Main Entry Point ---
if __name__ == "__main__":
    print("🚀 Starting Terraform State Sync...")
    fetch_all_state_files()
    print("✅ Script finished.")
