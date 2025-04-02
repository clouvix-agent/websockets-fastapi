from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.chatbot import process_query
from app.core.tf_generator import TerraformRequest
import json
import os
from jose import jwt, JWTError
from app.auth.utils import SECRET_KEY, ALGORITHM

router = APIRouter(
    prefix="",
    tags=["general"]
)

@router.get("/")
async def root():
    return {"message": "Welcome to Clouvix"}

@router.get("/hello")
async def hello():
    return {"message": "Hello"}

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
