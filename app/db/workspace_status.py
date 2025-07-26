from sqlalchemy.orm import Session
from app.models.workspace_status import WorkspaceStatus
from app.schemas.workspace_status import WorkspaceStatusCreate

def create_workspace_status(db: Session, status_data: WorkspaceStatusCreate) -> WorkspaceStatus:
    db_status = WorkspaceStatus(**status_data.model_dump())
    db.add(db_status)
    db.commit()
    db.refresh(db_status)
    return db_status

def get_workspace_status_by_id(db: Session, status_id: int) -> WorkspaceStatus:
    return db.query(WorkspaceStatus).filter(WorkspaceStatus.id == status_id).first()

def get_statuses_for_user(db: Session, user_id: int) -> list[WorkspaceStatus]:
    return db.query(WorkspaceStatus).filter(WorkspaceStatus.userid == user_id).all()

def get_status_for_project(db: Session, user_id: int, project_name: str) -> WorkspaceStatus:
    return db.query(WorkspaceStatus).filter(
        WorkspaceStatus.userid == user_id,
        WorkspaceStatus.project_name == project_name
    ).first()

def create_or_update_workspace_status(db: Session, status_data: WorkspaceStatusCreate) -> WorkspaceStatus:
    print("Inside Create or update")
    existing_status = db.query(WorkspaceStatus).filter(
        WorkspaceStatus.userid == status_data.userid,
        WorkspaceStatus.project_name == status_data.project_name
    ).first()

    print(existing_status)

    if existing_status:
        existing_status.status = status_data.status
        db.commit()
        db.refresh(existing_status)
        return existing_status
    else:
        new_status = WorkspaceStatus(**status_data.model_dump())
        db.add(new_status)
        db.commit()
        db.refresh(new_status)
        return new_status