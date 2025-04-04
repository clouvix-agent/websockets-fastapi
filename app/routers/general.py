from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.chatbot import process_query
from app.core.tf_generator import TerraformRequest
import json
import os
from jose import jwt, JWTError
from app.auth.utils import SECRET_KEY, ALGORITHM
from sqlalchemy.orm import Session
from fastapi import Depends
from app.database import get_db
from app.models.workspace import Workspace
from app.models.connection import Connection
from pydantic import BaseModel
from typing import List
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer

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
async def get_workspaces(db: Session = Depends(get_db)):
    workspaces = db.query(Workspace).all()
    response = []
    for workspace in workspaces:
        response.append({
            "id": workspace.wsid,
            "projectName": workspace.wsname,
            "terraformStatus": "unknown",  # Placeholder, replace with actual status if available
            "lastRun": "unknown",  # Placeholder, replace with actual last run time if available
            "terraformFileLocation": workspace.filelocation,
            "terraformStateFileLocation": "unknown"  # Placeholder, replace with actual state file location if available
        })
    return response

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        # ✅ Step 1: Extract token from query param (NOT from headers)
        token = websocket.query_params.get("token")
        print("🔐 Received token:", token)

        if not token:
            print("❌ No token provided")
            await websocket.close(code=1008)
            return

        # ✅ Step 2: Decode token and extract user ID
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            print(payload)
            user_id = payload.get("id")
            print("✅ User ID:", user_id)

            if not user_id:
                print("❌ Token decoded but no user_id found")
                await websocket.close(code=1008)
                return

        except JWTError as e:
            print("❌ Invalid JWT:", str(e))
            await websocket.close(code=1008)
            return

        # ✅ Step 3: Handle WebSocket messages with user_id
        while True:
            message = await websocket.receive_text()

            try:
                response = await process_query(message, user_id=user_id)

                await websocket.send_json({
                    "type": "step",
                    "content": response
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
async def generate_terraform(request: TerraformRequest):
    # Create architecture_json directory if it doesn't exist
    os.makedirs("architecture_json", exist_ok=True)
    
    print("Received request")
    print(f"Received request: {request}")
    with open("architecture_json/request.json", "w") as f:
        json.dump(request.model_dump(), f)
    return {"message": "Terraform request saved"}

@router.post("/api/connections")
async def save_credentials(
    request: CredentialRequest,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        # Decode the JWT token
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("id")
            if not user_id:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid token: No user ID found"
                )
        except JWTError as e:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid token: {str(e)}"
            )

        # Create a new connection entry
        new_connection = Connection(
            userid=user_id,  # Use the decoded user_id
            type=request.serviceId,
            connection_json=json.dumps([var.dict() for var in request.variables]),
            connection_bucket_name=request.bucketName
        )
        
        # Add to database
        db.add(new_connection)
        db.commit()
        db.refresh(new_connection)
        
        return {
            "message": "Credentials saved successfully",
            "connection_id": new_connection.connid
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error saving credentials: {str(e)}"
        )

@router.get("/api/connections/{serviceId}")
async def get_connections(
    serviceId: str,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        # Decode the JWT token
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("id")
            if not user_id:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid token: No user ID found"
                )
        except JWTError as e:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid token: {str(e)}"
            )

        # Query connections
        connections = db.query(Connection).filter(
            Connection.userid == user_id,
            Connection.type == serviceId
        ).all()

        # Format response
        response = [{
            "bucketName": conn.connection_bucket_name,
            "variables": json.loads(conn.connection_json)
        } for conn in connections]

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching connections: {str(e)}"
        )
