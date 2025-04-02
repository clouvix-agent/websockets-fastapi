from sqlalchemy.orm import Session
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceCreate

def create_workspace(db: Session, workspace: WorkspaceCreate) -> Workspace:
    """
    Create a new workspace in the database.
    
    Args:
        db: Database session
        workspace: Workspace data to be inserted
        
    Returns:
        Created workspace object
    """
    db_workspace = Workspace(**workspace.model_dump())
    db.add(db_workspace)
    db.commit()
    db.refresh(db_workspace)
    return db_workspace

def get_workspace(db: Session, workspace_id: int) -> Workspace:
    """
    Get a workspace by ID.
    
    Args:
        db: Database session
        workspace_id: ID of the workspace to retrieve
        
    Returns:
        Workspace object if found, None otherwise
    """
    return db.query(Workspace).filter(Workspace.id == workspace_id).first()

def get_user_workspaces(db: Session, user_id: int) -> list[Workspace]:
    """
    Get all workspaces for a specific user.
    
    Args:
        db: Database session
        user_id: ID of the user
        
    Returns:
        List of workspaces belonging to the user
    """
    return db.query(Workspace).filter(Workspace.userid == user_id).all() 