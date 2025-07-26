from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
import boto3
import json

from app.database import get_db
from app.models.connection import Connection
from app.models.infrastructure_inventory import InfrastructureInventory
from app.auth.utils import SECRET_KEY, ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter(
    prefix="/api/existingresource",
    tags=["existing_resource"]
)

@router.get("/")
async def fetch_grouped_new_aws_resources(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    # Decode JWT and extract user_id
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Get AWS credentials from DB
    conn = (
        db.query(Connection)
        .filter(Connection.userid == user_id, Connection.type == "aws")
        .first()
    )
    if not conn or not conn.connection_json:
        raise HTTPException(status_code=404, detail="AWS connection not found for this user.")

    data = conn.connection_json
    if isinstance(data, str):
        data = json.loads(data)

    # Make dict of creds
    if isinstance(data, dict):
        creds = data
    elif isinstance(data, list):
        creds = {e.get("key"): e.get("value") for e in data if isinstance(e, dict)}
    else:
        raise HTTPException(status_code=400, detail="Unsupported connection_json format")

    try:
        access_key = creds["AWS_ACCESS_KEY_ID"]
        secret_key = creds["AWS_SECRET_ACCESS_KEY"]
        region = creds.get("RESOURCE_EXPLORER_REGION")
    except KeyError as missing:
        raise HTTPException(status_code=400, detail=f"Missing {missing} in AWS credentials")

    if not region:
        raise HTTPException(status_code=400, detail="Missing RESOURCE_EXPLORER_REGION in AWS connection")

    # Fetch existing ARNs
    rows = (
        db.query(InfrastructureInventory.arn)
        .filter(InfrastructureInventory.user_id == user_id)
        .all()
    )
    existing_arns = {row[0] for row in rows}

    # Call AWS Resource Explorer and group results
    grouped_resources = {}

    try:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        rex = session.client("resource-explorer-2", region_name=region)
        paginator = rex.get_paginator("search")

        for page in paginator.paginate(QueryString="*"):
            for res in page.get("Resources", []):
                arn = res.get("Arn")
                if not arn or arn in existing_arns:
                    continue

                # Parse the ARN and resource type
                service = res.get("Service", "Unknown")
                resource_type = res.get("ResourceType", "Unknown")
                key = f"{service}:{resource_type}"

                grouped_resources.setdefault(key, []).append(arn)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error accessing AWS Resource Explorer: {str(e)}")

    return grouped_resources
