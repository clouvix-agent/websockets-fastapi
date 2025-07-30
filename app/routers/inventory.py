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
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    inventories = db.query(InfrastructureInventory).filter(
        InfrastructureInventory.user_id == user_id
    ).all()

    return [inv.__dict__ for inv in inventories]


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

@router.get("/{project_name}")
async def get_workspace_inventory(
    project_name: str,
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

    # Fetch all inventory items for the user and specific project
    inventories = db.query(InfrastructureInventory).filter(
        InfrastructureInventory.user_id == user_id,
        InfrastructureInventory.project_name == project_name
    ).all()

    if not inventories:
        return {"message": f"No inventory found for project '{project_name}'"}

    # Build the simple response
    result = []
    for item in inventories:
        result.append({
            "resource_type": item.resource_type,
            "resource_name": item.resource_name,
            "arn": item.arn
        })

    return result
