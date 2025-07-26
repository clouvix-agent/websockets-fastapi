from sqlalchemy.orm import Session
from app.models.drift import DriftDetection
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

def save_drift_result(db: Session, userid: int, project_name: str, drift_reason: str):
    """
    Inserts or updates drift detection result if drift is present.
    """
    existing = db.query(DriftDetection).filter_by(userid=userid, project_name=project_name).first()
    now_ist = datetime.now(IST)

    if existing:
        existing.drift_reason = drift_reason
        existing.updated_time = now_ist
        print(f"📝 Drift updated for {project_name} (user {userid})")
    else:
        new_entry = DriftDetection(
            userid=userid,
            project_name=project_name,
            drift_reason=drift_reason,
            updated_time=now_ist
        )
        db.add(new_entry)
        print(f"🆕 Drift inserted for {project_name} (user {userid})")

    db.commit()

def fetch_drift_reason(db: Session, userid: int, project_name: str) -> str:
    """
    Fetches the drift_reason for the given user and project from the drift_detection table.

    Args:
        db (Session): SQLAlchemy DB session
        userid (int): User ID
        project_name (str): Name of the Terraform project

    Returns:
        str: Drift reason text if found, or empty string if not found
    """
    result = db.query(DriftDetection).filter_by(userid=userid, project_name=project_name).first()
    if result and result.drift_reason:
        return result.drift_reason.strip()
    return ""

def delete_drift_result(db: Session, userid: int, project_name: str) -> bool:
    """
    Deletes a drift detection record for a given user and project after it has been resolved.

    Args:
        db (Session): SQLAlchemy DB session.
        userid (int): The user's ID.
        project_name (str): The name of the project.

    Returns:
        bool: True if a record was deleted, False otherwise.
    """
    existing_drift = db.query(DriftDetection).filter_by(userid=userid, project_name=project_name).first()

    if existing_drift:
        db.delete(existing_drift)
        db.commit()
        print(f"🗑️ Drift record deleted for {project_name} (user {userid})")
        return True
    
    print(f"ℹ️ No drift record found to delete for {project_name} (user {userid})")
    return False