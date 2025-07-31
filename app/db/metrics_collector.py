from sqlalchemy.orm import Session
from app.models.metrics_collector import MetricsCollection
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

def convert_datetimes(obj):
    """
    Recursively converts datetime objects to ISO format strings in a nested dict or list.
    """
    if isinstance(obj, dict):
        return {k: convert_datetimes(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_datetimes(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj

def create_or_update_metrics(
    db: Session,
    userid: int,
    arn: str,
    resource_type: str,
    metrics_data: dict,
    additional_info: dict = None
):
    """
    Inserts or updates metrics data for a given user and ARN.
    Also updates additional_info (e.g., instance type).
    """
    now_ist = datetime.now(IST)

    # Ensure all datetime values are JSON serializable
    cleaned_metrics_data = convert_datetimes(metrics_data)
    cleaned_additional_info = convert_datetimes(additional_info or {})

    existing = db.query(MetricsCollection).filter_by(userid=userid, arn=arn).first()

    if existing:
        existing.metrics_data = cleaned_metrics_data
        existing.resource_type = resource_type
        existing.additional_info = cleaned_additional_info
        existing.updated_at = now_ist
        print(f"🔄 Updated metrics for ARN: {arn} (User {userid})")
    else:
        new_entry = MetricsCollection(
            userid=userid,
            arn=arn,
            resource_type=resource_type,
            metrics_data=cleaned_metrics_data,
            additional_info=cleaned_additional_info,
            created_at=now_ist,
            updated_at=now_ist
        )
        db.add(new_entry)
        print(f"🆕 Inserted new metrics for ARN: {arn} (User {userid})")

    db.commit()



def fetch_all_collected_metrics(db: Session):
    """
    Fetch all stored metrics from the metrics_collection table.

    Args:
        db (Session): SQLAlchemy session.

    Returns:
        List[dict]: List of collected metric entries with relevant fields.
    """
    records = db.query(MetricsCollection).all()

    result = []
    for record in records:
        result.append({
            "userid": record.userid,
            "arn": record.arn,
            "resource_type": record.resource_type,
            "metrics_data": record.metrics_data,
            "additional_info": record.additional_info
        })

    return result
