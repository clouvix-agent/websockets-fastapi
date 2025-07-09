from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.chatbot import process_query
from app.core.tf_generator import TerraformRequest
import json
import os
import requests
from minio import Minio
from jose import jwt, JWTError
from app.auth.utils import SECRET_KEY, ALGORITHM
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import Depends
from app.database import get_db
from app.models.workspace import Workspace
from app.models.connection import Connection
from pydantic import BaseModel
from typing import List
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
import boto3
import datetime
import json
import os
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter(
    prefix="",
    tags=["general"]
)

class CredentialVariable(BaseModel):
    key: str
    value: str

class CredentialRequest(BaseModel):
    serviceId: str
    bucketName: str
    variables: List[CredentialVariable]

@router.get("/")
async def root():
    return {"message": "Welcome to Clouvix"}

@router.get("/hello")
async def hello():
    return {"message": "Hello"}

@router.get("/api/workspaces")
async def get_workspaces(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        # Decode the JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    # Fetch workspaces belonging to the authenticated user
    workspaces = db.query(Workspace).filter(Workspace.userid == user_id).all()
    
    response = []
    for workspace in workspaces:
        response.append({
            "id": workspace.wsid,
            "projectName": workspace.wsname,
            "terraformStatus": "unknown",  # Placeholder
            "lastRun": "unknown",  # Placeholder
            "terraformFileLocation": workspace.filelocation,
            "terraformStateFileLocation": "unknown"  # Placeholder
        })
    return response

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        token = websocket.query_params.get("token")
        print("🔐 Received token:", token)

        if not token:
            print("❌ No token provided")
            await websocket.close(code=1008)
            return

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("id")
            print("✅ User ID:", user_id)

            if not user_id:
                await websocket.close(code=1008)
                return

        except JWTError as e:
            print("❌ Invalid JWT:", str(e))
            await websocket.close(code=1008)
            return

        while True:
            message = await websocket.receive_text()

            try:
                response = await process_query(message, user_id=user_id)

                await websocket.send_json({
                    "type": "step",
                    "content": response["reply"],
                    "suggestions": response.get("suggestions", [])
                })

                await websocket.send_json({
                    "type": "complete",
                    "status": "success"
                })

            except Exception as e:
                print(f"❌ Error processing message: {str(e)}")
                await websocket.send_json({
                    "type": "error",
                    "content": str(e)
                })

    except WebSocketDisconnect:
        print("❌ Client disconnected")

# Receive a object at /api/generate_terraform
@router.post("/api/generate_terraform")
async def generate_terraform(request: TerraformRequest, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    # Create architecture_json directory if it doesn't exist
    os.makedirs("architecture_json", exist_ok=True)
    
    print("Received request")
    print(f"Received request: {request}")
    
    try:
        # Decode the JWT token to get the user ID
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
            
        # Save the architecture JSON to the database directly using SQL
        architecture_json = request.model_dump()
        project_name = request.project_name
        
        # Check if architecture already exists for this user and project using raw SQL
        result = db.execute(
            text("SELECT COUNT(*) FROM architecture WHERE userid = :userid AND project_name = :project_name"),
            {"userid": user_id, "project_name": project_name}
        ).fetchone()
        
        if result and result[0] > 0:
            # Raise an error for duplicate project name
            raise HTTPException(
                status_code=409,
                detail=f"Project name '{project_name}' already exists for this user. Please use a different project name."
            )
        else:
            # Create new architecture
            db.execute(
                text("INSERT INTO architecture (userid, architecture_json, project_name) VALUES (:userid, :architecture_json, :project_name)"),
                {"userid": user_id, "architecture_json": json.dumps(architecture_json), "project_name": project_name}
            )
            db.commit()
            print(f"Created new architecture for user {user_id}, project {project_name}")
            
            # First save to file temporarily (in case we need it for backward compatibility)
            architecture_file_path = "architecture_json/request.json"
            with open(architecture_file_path, "w") as f:
                json.dump(architecture_json, f)
            
            # Then delete the file after saving to database
            try:
                os.remove(architecture_file_path)
                print(f"Deleted architecture file: {architecture_file_path}")
                
                # Also delete the directory if it's empty
                architecture_dir = os.path.dirname(architecture_file_path)
                if os.path.exists(architecture_dir) and not os.listdir(architecture_dir):
                    os.rmdir(architecture_dir)
                    print(f"Deleted empty directory: {architecture_dir}")
            except Exception as e:
                print(f"Warning: Could not delete architecture file or directory: {str(e)}")
        
        # Return success response
        return {"message": "Terraform request saved to database successfully"}
        
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except HTTPException as e:
        # Re-raise HTTP exceptions (like our duplicate project error)
        print(f"HTTP Exception: {e.detail}")
        # No need to save to file on error
        raise
    except Exception as e:
        print(f"Error saving architecture to database: {str(e)}")
        # Only save to file if there was a database error (as a fallback)
        architecture_file_path = "architecture_json/request.json"
        architecture_dir = os.path.dirname(architecture_file_path)
        
        # Create directory if it doesn't exist
        if not os.path.exists(architecture_dir):
            os.makedirs(architecture_dir, exist_ok=True)
            
        # Save to file as fallback
        with open(architecture_file_path, "w") as f:
            json.dump(request.model_dump(), f)
            
        return {"message": "Error saving to database. Architecture saved to file as fallback.", "error": str(e)}
    
    # Load environment variables
load_dotenv()

    # Create AWS session with credentials from environment variables
def get_aws_session():
    return boto3.Session(
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY'),
        aws_secret_access_key=os.getenv('AWS_SECRET_KEY'),
        region_name=os.getenv('AWS_REGION', 'us-east-1')  # Default to us-east-1 if not specified
    )

    # Get AWS session
aws_session = get_aws_session()

    # Helper function to fetch CloudWatch metrics
def fetch_cpu_utilization(resource_id, namespace, metric_name, dimension_name):
    cloudwatch_client = aws_session.client("cloudwatch")
    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(hours=1)  # Fetch metrics for the last hour

    response = cloudwatch_client.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=[{"Name": dimension_name, "Value": resource_id}],
        StartTime=start_time,
        EndTime=end_time,
        Period=300,  # 5-minute intervals
        Statistics=["Average"],
    )

    if response["Datapoints"]:
        return response["Datapoints"][-1]["Average"]  # Most recent datapoint
    return None

    # Fetch detailed S3 bucket information
def fetch_s3_buckets():
    s3_client = aws_session.client("s3")
    response = s3_client.list_buckets()
    buckets = []
    for bucket in response.get("Buckets", []):
        bucket_name = bucket["Name"]
        try:
            bucket_location = s3_client.get_bucket_location(Bucket=bucket_name)
            bucket_acl = s3_client.get_bucket_acl(Bucket=bucket_name)
            buckets.append({
                "Name": bucket_name,
                "CreationDate": bucket["CreationDate"].strftime("%Y-%m-%d %H:%M:%S"),
                "Location": bucket_location.get("LocationConstraint"),
                "ACL": bucket_acl.get("Grants"),
            })
        except Exception as e:
            buckets.append({"Name": bucket_name, "Error": str(e)})
    return buckets

    # Fetch detailed EC2 instance information with CPU utilization
def fetch_ec2_instances():
    ec2_client = aws_session.client("ec2")
    response = ec2_client.describe_instances()
    instances = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instance_id = instance["InstanceId"]
            cpu_utilization = fetch_cpu_utilization(
                resource_id=instance_id,
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimension_name="InstanceId",
            )
            instances.append({
                "InstanceId": instance_id,
                "State": instance["State"]["Name"],
                "PublicIP": instance.get("PublicIpAddress"),
                "PrivateIP": instance.get("PrivateIpAddress"),
                "InstanceType": instance["InstanceType"],
                "LaunchTime": instance["LaunchTime"].strftime("%Y-%m-%d %H:%M:%S"),
                "Tags": instance.get("Tags", []),
                "SecurityGroups": instance.get("SecurityGroups", []),
                "CPUUtilization": cpu_utilization,
            })
    return instances

    # Fetch detailed DynamoDB table information
def fetch_dynamodb_tables():
    dynamodb_client = aws_session.client("dynamodb")
    response = dynamodb_client.list_tables()
    tables = []
    for table_name in response.get("TableNames", []):
        try:
            table_info = dynamodb_client.describe_table(TableName=table_name)
            tables.append({
                "TableName": table_name,
                "ItemCount": table_info["Table"]["ItemCount"],
                "CreationDateTime": table_info["Table"]["CreationDateTime"].strftime("%Y-%m-%d %H:%M:%S"),
                "TableStatus": table_info["Table"]["TableStatus"],
                "ProvisionedThroughput": table_info["Table"]["ProvisionedThroughput"],
            })
        except Exception as e:
            tables.append({"TableName": table_name, "Error": str(e)})
    return tables

    # Fetch detailed ECS cluster information
def fetch_ecs_clusters():
    ecs_client = aws_session.client("ecs")
    response = ecs_client.list_clusters()
    clusters = []
    for cluster_arn in response.get("clusterArns", []):
        try:
            cluster_info = ecs_client.describe_clusters(clusters=[cluster_arn])
            clusters.append(cluster_info["clusters"][0])
        except Exception as e:
            clusters.append({"ClusterArn": cluster_arn, "Error": str(e)})
    return clusters

    # Fetch detailed RDS instance information with CPU utilization
def fetch_rds_instances():
    rds_client = aws_session.client("rds")
    response = rds_client.describe_db_instances()
    instances = []
    for db in response["DBInstances"]:
        db_instance_id = db["DBInstanceIdentifier"]
        cpu_utilization = fetch_cpu_utilization(
            resource_id=db_instance_id,
            namespace="AWS/RDS",
            metric_name="CPUUtilization",
            dimension_name="DBInstanceIdentifier",
        )
        instances.append({
            "DBInstanceIdentifier": db_instance_id,
            "DBInstanceClass": db["DBInstanceClass"],
            "Engine": db["Engine"],
            "EngineVersion": db["EngineVersion"],
            "Status": db["DBInstanceStatus"],
            "Endpoint": db["Endpoint"]["Address"] if "Endpoint" in db else None,
            "AllocatedStorage": db["AllocatedStorage"],
            "AvailabilityZone": db["AvailabilityZone"],
            "MultiAZ": db["MultiAZ"],
            "CPUUtilization": cpu_utilization,
        })
    return instances

    # Fetch detailed ECR repository information
def fetch_ecr_repositories():
    ecr_client = aws_session.client("ecr")
    response = ecr_client.describe_repositories()
    repositories = []
    for repo in response.get("repositories", []):
        repositories.append({
            "RepositoryName": repo["repositoryName"],
            "Arn": repo["repositoryArn"],
            "CreatedAt": repo["createdAt"].strftime("%Y-%m-%d %H:%M:%S"),
            "ImageTagMutability": repo["imageTagMutability"],
            "EncryptionConfiguration": repo.get("encryptionConfiguration"),
        })
    return repositories

    # Fetch detailed EKS cluster information
def fetch_eks_clusters():
    eks_client = aws_session.client("eks")
    response = eks_client.list_clusters()
    clusters = []
    for cluster_name in response.get("clusters", []):
        try:
            cluster_info = eks_client.describe_cluster(name=cluster_name)
            clusters.append(cluster_info["cluster"])
        except Exception as e:
            clusters.append({"ClusterName": cluster_name, "Error": str(e)})
    return clusters

    # Fetch detailed Lambda function information
def fetch_lambda_functions():
    lambda_client = aws_session.client("lambda")
    response = lambda_client.list_functions()
    functions = []
    for func in response.get("Functions", []):
        functions.append({
            "FunctionName": func["FunctionName"],
            "Runtime": func["Runtime"],
            "Handler": func["Handler"],
            "MemorySize": func["MemorySize"],
            "Timeout": func["Timeout"],
            "LastModified": func["LastModified"],
            "Environment": func.get("Environment"),
        })
    return functions

    # Build the AWS Inventory
def build_inventory():
    inventory = {
        "S3": fetch_s3_buckets(),
        "EC2": fetch_ec2_instances(),
        "DynamoDB": fetch_dynamodb_tables(),
        "ECS": fetch_ecs_clusters(),
        "RDS": fetch_rds_instances(),
        "ECR": fetch_ecr_repositories(),
        "EKS": fetch_eks_clusters(),
        "Lambda": fetch_lambda_functions(),
     }
    return inventory

import threading
import time

def fetch_and_save_aws_inventory():
    while True:
        try:
            print("Fetching AWS Inventory...")
            inventory = build_inventory()

            # Save inventory to a JSON file
            with open("aws_comprehensive_inventory.json", "w") as f:
                json.dump(inventory, f, indent=4)

            print("AWS Inventory saved to 'aws_comprehensive_inventory.json'.")
        except Exception as e:
            print(f"Error fetching AWS inventory: {str(e)}")
        
        # Wait for 5 minutes before the next run
        time.sleep(86400)  # 24 hours

# # Start the background thread
# inventory_thread = threading.Thread(target=fetch_and_save_aws_inventory, daemon=True)
# inventory_thread.start() 
#This moved into all_threads.py

@router.get("/api/aws_inventory")
async def get_aws_inventory():
    try:
        with open("aws_comprehensive_inventory.json", "r") as f:
            inventory = json.load(f)
        return inventory
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching AWS inventory: {str(e)}")

# @router.get("/api/architectures")
# async def get_user_architectures(
#     db: Session = Depends(get_db),
#     token: str = Depends(oauth2_scheme)
# ):
#     """
#     Get all architecture projects for the authenticated user
#     """
#     try:
#         # Decode the JWT token
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("id")
#         if not user_id:
#             raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
            
#         # Query all architectures for this user
#         results = db.execute(
#             text("SELECT id, project_name, created_at, updated_at FROM architecture WHERE userid = :userid ORDER BY updated_at DESC"),
#             {"userid": user_id}
#         ).fetchall()
        
#         # Convert to list of dictionaries
#         architectures = []
#         for row in results:
#             architectures.append({
#                 "id": row[0],
#                 "project_name": row[1],
#                 "created_at": row[2].isoformat() if row[2] else None,
#                 "updated_at": row[3].isoformat() if row[3] else None
#             })
            
#         return architectures
        
#     except JWTError as e:
#         raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error retrieving architectures: {str(e)}")

# @router.get("/api/architecture/{project_name}")
# async def get_architecture_by_project_name(
#     project_name: str,
#     db: Session = Depends(get_db),
#     token: str = Depends(oauth2_scheme)
# ):
#     """
#     Get a specific architecture project by name for the authenticated user
#     """
#     try:
#         # Decode the JWT token
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("id")
#         if not user_id:
#             raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
            
#         # Query the architecture for this user and project name
#         result = db.execute(
#             text("SELECT id, architecture_json, created_at, updated_at FROM architecture WHERE userid = :userid AND project_name = :project_name"),
#             {"userid": user_id, "project_name": project_name}
#         ).fetchone()
        
#         if not result:
#             raise HTTPException(status_code=404, detail=f"Architecture project '{project_name}' not found")
            
#         # Return the architecture data
#         return {
#             "id": result[0],
#             "project_name": project_name,
#             "architecture_json": result[1],
#             "created_at": result[2].isoformat() if result[2] else None,
#             "updated_at": result[3].isoformat() if result[3] else None
#         }
        
#     except JWTError as e:
#         raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
#     except HTTPException as e:
#         # Re-raise HTTP exceptions
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error retrieving architecture: {str(e)}")

# @router.delete("/api/architecture/{project_name}")
# async def delete_architecture_by_project_name(
#     project_name: str,
#     db: Session = Depends(get_db),
#     token: str = Depends(oauth2_scheme)
# ):
#     """
#     Delete a specific architecture project by name for the authenticated user
#     """
#     try:
#         # Decode the JWT token
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("id")
#         if not user_id:
#             raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
            
#         # Delete the architecture for this user and project name
#         result = db.execute(
#             text("DELETE FROM architecture WHERE userid = :userid AND project_name = :project_name"),
#             {"userid": user_id, "project_name": project_name}
#         )
#         db.commit()
        
#         # Check if any rows were affected
#         if result.rowcount == 0:
#             raise HTTPException(status_code=404, detail=f"Architecture project '{project_name}' not found")
            
#         return {"message": f"Architecture project '{project_name}' successfully deleted"}
        
#     except JWTError as e:
#         raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
#     except HTTPException as e:
#         # Re-raise HTTP exceptions
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error deleting architecture: {str(e)}")