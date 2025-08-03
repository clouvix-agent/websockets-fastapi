# from langchain_core.runnables import RunnableConfig
# from langchain.tools import tool
# import os
# import shutil
# from sqlalchemy import create_engine, text
# from dotenv import load_dotenv

# from app.core.existing_to_tf import (
#     get_aws_credentials_from_db,
#     fetch_and_save_aws_resource_details,
#     generate_terraform_from_resource_details,
#     validate_and_fix_terraform_code,
#     import_and_apply_for_resource,
#     upload_terraform_to_minio,
#     DynamicAWSResourceInspector,
#     TEMP_DIR  # ✅ Needed for path reference
# )


# @tool
# def migration_tool(project_name: str, config: RunnableConfig, listofarn: list[str]) -> str:
#     """
#     Performs migration from existing AWS resources to Terraform-managed infrastructure.

#     Runs a full Terraform lifecycle from ARN list:
#     - Fetch AWS resource configuration from live infrastructure
#     - Generate Terraform HCL code using GPT
#     - Validate and fix the code using Terraform and OpenAI
#     - Import resources into Terraform state
#     - Apply Terraform configuration to verify state match
#     - Upload files to MinIO storage
#     - Update workspace status in the database
#     - Cleanup temporary working folder
#     """
#     try:
#         # ✅ 1. Extract user_id from LangChain config
#         user_id = config['configurable'].get('user_id', 'unknown')
#         if user_id == 'unknown':
#             return "❌ user_id not found in config['configurable']"

#         # ✅ 2. Get AWS credentials
#         try:
#             ACCESS_KEY, SECRET_KEY = get_aws_credentials_from_db(user_id=user_id)
#         except ValueError as e:
#             return str(e)

#         # ✅ 3. Initialize AWS Inspector
#         inspector = DynamicAWSResourceInspector(ACCESS_KEY, SECRET_KEY, region="us-east-1")

#         # ✅ 4. Fetch & save details to temp file
#         fetch_and_save_aws_resource_details(
#             arns=listofarn,
#             inspector=inspector,
#             project_name=project_name
#         )

#         # ✅ 5. Generate Terraform code using GPT
#         terraform_code = generate_terraform_from_resource_details(
#             arns=listofarn,
#             inspector=inspector
#         )

#         # ✅ 6. Validate and fix the code
#         final_tf_code = validate_and_fix_terraform_code(terraform_code)

#         # ✅ 7. Import and Apply
#         main_tf_path = os.path.join(TEMP_DIR, "main.tf")
#         result = import_and_apply_for_resource(
#             main_tf_path=main_tf_path,
#             arns=listofarn,
#             user_id=user_id,
#             project_name=project_name
#         )

#         # ✅ 8. Upload to MinIO
#         upload_status = upload_terraform_to_minio(
#             local_tf_dir=TEMP_DIR,
#             user_id=user_id,
#             project_name=project_name
#         )

#         # ✅ 9. Cleanup
#         if os.path.exists(TEMP_DIR):
#             shutil.rmtree(TEMP_DIR)

#         return f"""
# ✅ Migration Completed from AWS → Terraform

# 📝 Terraform Apply Output:
# {result}

# ☁️ Upload Status:
# {upload_status}
# """

#     except Exception as e:
#         return f"❌ Unexpected error occurred during migration: {str(e)}"


from langchain_core.runnables import RunnableConfig
from langchain.tools import tool
import os
import shutil
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import tempfile

from app.core.existing_to_tf import (
    get_aws_credentials_from_db,
    fetch_and_save_aws_resource_details,
    generate_terraform_from_resource_details,
    validate_and_fix_terraform_code,
    import_and_apply_for_resource,
    upload_terraform_to_minio,
    DynamicAWSResourceInspector,
    TEMP_DIR  # ✅ Needed for path reference
)


@tool
def migration_tool(project_name: str, config: RunnableConfig, listofarn: list[str]) -> str:
    """
    Performs migration from existing AWS resources to Terraform-managed infrastructure.

    Runs a full Terraform lifecycle from ARN list:
    - Fetch AWS resource configuration from live infrastructure
    - Generate Terraform HCL code using GPT
    - Validate and fix the code using Terraform and OpenAI
    - Import resources into Terraform state
    - Apply Terraform configuration to verify state match
    - Upload files to MinIO storage
    - Insert workspace into the database
    - Cleanup temporary working folder
    """
    temp_dir_path = tempfile.mkdtemp()
    try:
        # 1. Extract user_id from LangChain config
        user_id = config['configurable'].get('user_id', 'unknown')
        if user_id == 'unknown':
            return "❌ user_id not found in config['configurable']"

        # 2. Get AWS credentials
        try:
            ACCESS_KEY, SECRET_KEY = get_aws_credentials_from_db(user_id=user_id)
        except ValueError as e:
            return str(e)

        # 3. Initialize AWS Inspector
        inspector = DynamicAWSResourceInspector(ACCESS_KEY, SECRET_KEY, region="us-east-1")

        # 4. Fetch & save details to temp file
        fetch_and_save_aws_resource_details(
            arns=listofarn,
            inspector=inspector,
            project_name=project_name,
            output_dir=temp_dir_path
        )

        # 5. Generate Terraform code using GPT
        terraform_code = generate_terraform_from_resource_details(
            arns=listofarn,
            inspector=inspector
        )
        print(terraform_code)
        # 6. Validate and fix the code
        final_tf_code = validate_and_fix_terraform_code(terraform_code,working_dir=temp_dir_path)
        print(final_tf_code)
        # 7. Import and Apply
        main_tf_path = os.path.join(temp_dir_path, "main.tf")
        result = import_and_apply_for_resource(
            main_tf_path=main_tf_path,
            arns=listofarn,
            user_id=user_id,
            project_name=project_name,
            aws_access_key=ACCESS_KEY,
            aws_secret_key=SECRET_KEY,
            region="us-east-1"
        )

        # 8. Upload to MinIO
        upload_status = upload_terraform_to_minio(
            local_tf_dir=temp_dir_path,
            user_id=user_id,
            project_name=project_name
        )

        # 9. Insert into workspaces table using DATABASE_URL
        load_dotenv()
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return "❌ DATABASE_URL not found in environment"

        engine = create_engine(db_url)

        insert_query = text("""
            INSERT INTO workspaces (userid, wsname, filetype, filelocation, diagramjson, githublocation)
            VALUES (:userid, :wsname, :filetype, :filelocation, :diagramjson, :githublocation)
        """)

        try:
            with engine.connect() as connection:
                connection.execute(insert_query, {
                    "userid": user_id,
                    "wsname": project_name,
                    "filetype": "terraform",
                    "filelocation": f"{project_name}_terraform/main.tf",
                    "diagramjson": '{}',
                    "githublocation": None
                })
                connection.commit()
            db_status = "✅ Workspace record inserted into database."
        except Exception as db_err:
            db_status = f"❌ Failed to insert workspace: {str(db_err)}"

        # 10. Cleanup
        if os.path.exists(temp_dir_path):
            shutil.rmtree(temp_dir_path)

        return f"""
Migration Completed from AWS → Terraform

Terraform Apply Output:
{result}

Upload Status:
{upload_status}

Database:
{db_status}
"""

    except Exception as e:
        return f"❌ Unexpected error occurred during migration: {str(e)}"
