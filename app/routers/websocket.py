# from fastapi import WebSocket, WebSocketDisconnect
# from app.core.chatbot import process_query
# from fastapi import APIRouter, status
# from app.auth.utils import SECRET_KEY, ALGORITHM
# from jose import JWTError, jwt
# from sqlalchemy.orm import Session
# from app.database import get_db
# from typing import Optional

# router = APIRouter(tags=["websocket"])

# def get_token_from_query(websocket: WebSocket) -> Optional[str]:
#     # Get token from query parameters
#     return websocket.query_params.get("token")

# def verify_token(token: str) -> Optional[str]:
#     if not token:
#         return None
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         username: str = payload.get("sub")
#         if username is None:
#             return None
#         return username
#     except JWTError:
#         return None

# @router.websocket("/ws/chat/new")
# async def websocket_endpoint(websocket: WebSocket):
#     # Verify token before accepting connection
    
#     token = get_token_from_query(websocket)
#     username = verify_token(token) if token else None
    
#     if not username:
#         await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
#         return
        
#     await websocket.accept()
#     print(f"Authenticated connection established for user: {username}")
    
#     try:
#         while True:
#             message = await websocket.receive_text()
            
#             try:
#                 response = await process_query(message)
#                 try:
#                     await websocket.send_json({
#                         "type": "step",
#                         "content": response
#                     })
#                 except WebSocketDisconnect:
#                     print("Client disconnected during processing")
#                     return
                
#                 try:
#                     await websocket.send_json({
#                         "type": "complete",
#                         "status": "success"
#                     })
#                 except WebSocketDisconnect:
#                     print("Client disconnected during completion")
#                     return
                    
#             except Exception as e:
#                 print(f"Error processing message: {str(e)}")
#                 try:
#                     await websocket.send_json({
#                         "type": "error",
#                         "content": str(e)
#                     })
#                 except WebSocketDisconnect:
#                     print("Client disconnected during error")
#                     return
                
#     except WebSocketDisconnect:
#         print(f"Client disconnected: {username}") 
