from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from app.auth.utils import SECRET_KEY, ALGORITHM
from app.database import get_db
from app.models.workspace_status import WorkspaceStatus  # Make sure your model is in this path
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter(
    prefix="/api/workspace-status",
    tags=["workspace-status"]
)

@router.get("/{project_name}")
async def get_workspace_status(
    project_name: str,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        # Decode JWT token to extract user_id
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    try:
        # Query the workspace status for the logged-in user & specific project
        workspace = db.query(WorkspaceStatus).filter(
            WorkspaceStatus.userid == user_id,
            WorkspaceStatus.project_name == project_name
        ).first()

        if not workspace:
            raise HTTPException(
                status_code=404,
                detail=f"No workspace found for project '{project_name}'"
            )

        return {
            "userid": workspace.userid,
            "project_name": workspace.project_name,
            "status": workspace.status
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching workspace status: {str(e)}")
