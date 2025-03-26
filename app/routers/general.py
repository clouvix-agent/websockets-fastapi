from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.chatbot import process_query
from app.core.tf_generator import TerraformRequest
import json
import os

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
        while True:
            message = await websocket.receive_text()
            
            try:
                response = await process_query(message)
                try:
                    await websocket.send_json({
                        "type": "step",
                        "content": response
                    })
                except WebSocketDisconnect:
                    print("Client disconnected during processing")
                    return
                
                try:
                    await websocket.send_json({
                        "type": "complete",
                        "status": "success"
                    })
                except WebSocketDisconnect:
                    print("Client disconnected during completion")
                    return
                    
            except Exception as e:
                print(f"Error processing message: {str(e)}")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "content": str(e)
                    })
                except WebSocketDisconnect:
                    print("Client disconnected during error")
                    return
                
    except WebSocketDisconnect:
        print("Client disconnected") 

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
