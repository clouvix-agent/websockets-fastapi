from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from app.auth.utils import SECRET_KEY, ALGORITHM
from app.database import get_db
from app.models.infrastructure_inventory import InfrastructureInventory
from fastapi.security import OAuth2PasswordBearer
from typing import Dict, Any, List
from datetime import datetime

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter(
    prefix="/api/inventory",
    tags=["inventory"]
)


@router.get("")
async def get_user_inventory(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    # Decode token to get user_id
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    # Fetch all inventory items for the user
    inventories = db.query(InfrastructureInventory).filter(InfrastructureInventory.user_id == user_id).all()

    # Initialize the output
    inventory_data: Dict[str, List[Any]] = {
        "S3": [],
        "EC2": [],
        "DynamoDB": [],
        "ECS": [],
        "RDS": [],
        "ECR": [],
        "EKS": [],
        "Lambda": []
    }
    print(inventories)

    # Build the inventory JSON
    for item in inventories:
        service_type = item.resource_type
        attributes = item.attributes  # This is already a dict
        resource_name = item.resource_name
        print(resource_name)

        try:
            if service_type == "S3":
                s3_obj = {
                    "Name": attributes.get("bucket") or item.resource_identifier or resource_name,
                    "CreationDate": _format_date(attributes.get("creation_date")),
                    "Location": attributes.get("region") or None,
                    "ACL": attributes.get("acl") or []
                }
                inventory_data["S3"].append(s3_obj)

            elif service_type == "EC2":
                ec2_obj = {
                    "InstanceId": attributes.get("id"),
                    "State": attributes.get("instance_state") or attributes.get("state"),
                    "PublicIP": attributes.get("public_ip"),
                    "PrivateIP": attributes.get("private_ip"),
                    "InstanceType": attributes.get("instance_type"),
                    "LaunchTime": _format_date(attributes.get("launch_time")),
                    "Tags": attributes.get("tags", []),
                    "SecurityGroups": attributes.get("security_groups", []),
                    "CPUUtilization": attributes.get("cpu_utilization")
                }
                inventory_data["EC2"].append(ec2_obj)

            elif service_type == "RDS":
                rds_obj = {
                    "DBInstanceIdentifier": attributes.get("identifier") or item.resource_identifier,
                    "DBInstanceClass": attributes.get("instance_class"),
                    "Engine": attributes.get("engine"),
                    "EngineVersion": attributes.get("engine_version"),
                    "Status": attributes.get("status"),
                    "Endpoint": attributes.get("endpoint", {}).get("address"),
                    "AllocatedStorage": attributes.get("allocated_storage"),
                    "AvailabilityZone": attributes.get("availability_zone"),
                    "MultiAZ": attributes.get("multi_az"),
                    "CPUUtilization": attributes.get("cpu_utilization")
                }
                inventory_data["RDS"].append(rds_obj)

            elif service_type == "Lambda":
                lambda_obj = {
                    "FunctionName": attributes.get("function_name"),
                    "Runtime": attributes.get("runtime"),
                    "Handler": attributes.get("handler"),
                    "MemorySize": attributes.get("memory_size"),
                    "Timeout": attributes.get("timeout"),
                    "LastModified": attributes.get("last_modified"),
                    "Environment": attributes.get("environment")
                }
                inventory_data["Lambda"].append(lambda_obj)

            # Add similar mappings for other types if needed:
            # DynamoDB, ECS, ECR, EKS...

        except Exception as e:
            print(f"Error processing {service_type} - {item.id}: {e}")
            continue

    return inventory_data


def _format_date(date_val):
    """
    Utility function to format date into the required string format.
    Expects either a string or datetime object.
    """
    if isinstance(date_val, datetime):
        return date_val.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(date_val, str):
        try:
            # Try parsing ISO format
            dt = datetime.fromisoformat(date_val)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return date_val  # return as-is if not parseable
    return None
