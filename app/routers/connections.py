from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from app.auth.utils import SECRET_KEY, ALGORITHM
from app.database import get_db
from app.models.connection import Connection
from pydantic import BaseModel
from typing import List
import json
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter(
    prefix="/api/connections",
    tags=["connections"]
)

class CredentialVariable(BaseModel):
    key: str
    value: str

class CredentialRequest(BaseModel):
    serviceId: str
    bucketName: str
    variables: List[CredentialVariable]

# Save credentials
@router.post("")
async def save_credentials(
    request: CredentialRequest,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme) # pass in your OAuth2 scheme here
):
    from fastapi.security import OAuth2PasswordBearer
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
    token = await oauth2_scheme() if token is None else token

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    new_connection = Connection(
        userid=user_id,
        type=request.serviceId,
        connection_json=json.dumps([var.dict() for var in request.variables]),
        connection_bucket_name=request.bucketName
    )

    try:
        db.add(new_connection)
        db.commit()
        db.refresh(new_connection)
        return {
            "message": "Credentials saved successfully",
            "connection_id": new_connection.connid
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error saving credentials: {str(e)}")

# Get credentials
@router.get("/{serviceId}")
async def get_connections(
    serviceId: str,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)  # pass in your OAuth2 scheme here
):
    from fastapi.security import OAuth2PasswordBearer
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
    token = await oauth2_scheme() if token is None else token

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    connections = db.query(Connection).filter(
        Connection.userid == user_id,
        Connection.type == serviceId
    ).all()

    response = [{
        "bucketName": conn.connection_bucket_name,
        "variables": json.loads(conn.connection_json)
    } for conn in connections]

    return response

@router.put("/{serviceId}")
async def update_credentials(
    serviceId: str,
    request: CredentialRequest,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        # Decode JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    try:
        # Look for the existing connection
        connection = db.query(Connection).filter(
            Connection.userid == user_id,
            Connection.type == serviceId
        ).first()

        if not connection:
            raise HTTPException(
                status_code=404,
                detail=f"No existing credentials found for service ID '{serviceId}'"
            )

        # Update fields
        connection.connection_bucket_name = request.bucketName
        connection.connection_json = json.dumps([var.dict() for var in request.variables])

        db.commit()
        db.refresh(connection)

        return {
            "message": f"Credentials updated successfully for service ID '{serviceId}'",
            "connection_id": connection.connid
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating credentials: {str(e)}")

# class ConnectionWithRegionRequest(BaseModel):
#     serviceId: str
#     bucketName: str
#     variables: List[CredentialVariable]
#     resourceExplorerRegion: str

# # Endpoint 1: Create connection with resource explorer region
# @router.post("/createregion")
# async def create_connection_with_region(
#     request: ConnectionWithRegionRequest,
#     db: Session = Depends(get_db),
#     token: str = Depends(oauth2_scheme)
# ):
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("id")
#         if not user_id:
#             raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
#     except JWTError as e:
#         raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

#     new_connection = Connection(
#         userid=user_id,
#         type=request.serviceId,
#         connection_bucket_name=request.bucketName,
#         connection_json=json.dumps([var.dict() for var in request.variables]),
#         connection_region=request.resourceExplorerRegion
#     )

#     try:
#         db.add(new_connection)
#         db.commit()
#         db.refresh(new_connection)
#         return {
#             "message": "Connection created successfully",
#             "connection_id": new_connection.connid
#         }
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Error creating connection: {str(e)}")

# #to update existing one
# class UpdateRegionRequest(BaseModel):
#     resourceExplorerRegion: str

# @router.put("/update-region/{serviceId}")
# async def update_resource_explorer_region(
#     serviceId: str,
#     region_request: UpdateRegionRequest,
#     db: Session = Depends(get_db),
#     token: str = Depends(oauth2_scheme)
# ):
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("id")
#         if not user_id:
#             raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
#     except JWTError as e:
#         raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

#     connection = db.query(Connection).filter(
#         Connection.userid == user_id,
#         Connection.type == serviceId
#     ).first()

#     if not connection:
#         raise HTTPException(
#             status_code=404,
#             detail=f"No existing credentials found for service ID '{serviceId}'"
#         )

#     try:
#         connection.connection_region = region_request.resourceExplorerRegion
#         db.commit()
#         db.refresh(connection)
#         return {
#             "message": f"Resource Explorer Region updated successfully for service ID '{serviceId}'",
#             "connection_id": connection.connid
#         }
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Error updating resource explorer region: {str(e)}")

# @router.get("/region/{serviceId}")
# async def get_resource_explorer_region(
#     serviceId: str,
#     db: Session = Depends(get_db),
#     token: str = Depends(oauth2_scheme)
# ):
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         user_id = payload.get("id")
#         if not user_id:
#             raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
#     except JWTError as e:
#         raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

#     connection = db.query(Connection).filter(
#         Connection.userid == user_id,
#         Connection.type == serviceId
#     ).first()

#     if not connection:
#         raise HTTPException(
#             status_code=404,
#             detail=f"No existing connection found for service ID '{serviceId}'"
#         )

#     return {
#         "resourceExplorerRegion": getattr(connection, "connection_region", None)
#     }
