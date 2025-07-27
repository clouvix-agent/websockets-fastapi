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

def create_or_update_workspace(db: Session, workspace_data: WorkspaceCreate) -> Workspace:
    """
    Create a new workspace or update existing one based on userid and wsname.
    
    Args:
        db: Database session
        workspace_data: Workspace data to be inserted or updated
        
    Returns:
        Created or updated workspace object
    """
    # Check if workspace already exists for this user and name
    existing_workspace = db.query(Workspace).filter(
        Workspace.userid == workspace_data.userid,
        Workspace.wsname == workspace_data.wsname
    ).first()
    
    if existing_workspace:
        # Update existing workspace
        existing_workspace.filetype = workspace_data.filetype
        existing_workspace.filelocation = workspace_data.filelocation
        existing_workspace.diagramjson = workspace_data.diagramjson
        db.commit()
        db.refresh(existing_workspace)
        return existing_workspace
    else:
        # Create new workspace
        return create_workspace(db, workspace_data)

def get_workspace(db: Session, workspace_id: int) -> Workspace:
    """
    Get a workspace by ID.
    
    Args:
        db: Database session
        workspace_id: ID of the workspace to retrieve
        
    Returns:
        Workspace object if found, None otherwise
    """
    return db.query(Workspace).filter(Workspace.wsid == workspace_id).first()

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