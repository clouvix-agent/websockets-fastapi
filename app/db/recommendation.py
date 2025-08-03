from sqlalchemy.orm import Session
from app.models.recommendation import Recommendation
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from typing import Optional

def insert_or_update(
    db: Session,
    userid: int,
    resource_type: str,
    arn: str,
    recommendation_text: str,
    action: Optional[str] = None,
    impact: Optional[str] = None,
    savings: Optional[str] = None
):
    """
    Inserts a new recommendation or updates an existing one based on unique constraint
    (userid, resource_type, arn). Supports updating action, impact, and savings (as TEXT fields).
    """
    try:
        # Check if recommendation exists
        existing = db.query(Recommendation).filter_by(
            userid=userid,
            resource_type=resource_type,
            arn=arn
        ).first()

        if existing:
            existing.recommendation_text = recommendation_text
            existing.updated_timestamp = datetime.utcnow()

            if action is not None:
                existing.action = action
            if impact is not None:
                existing.impact = impact
            if savings is not None:
                existing.savings = savings

            print(f"🔄 Updated recommendation for ARN: {arn}")
        else:
            new_rec = Recommendation(
                userid=userid,
                resource_type=resource_type,
                arn=arn,
                recommendation_text=recommendation_text,
                updated_timestamp=datetime.utcnow(),
                action=action,
                impact=impact,
                savings=savings
            )
            db.add(new_rec)
            print(f"🆕 Inserted new recommendation for ARN: {arn}")

        db.commit()

    except IntegrityError as e:
        db.rollback()
        print(f"❌ IntegrityError while inserting/updating recommendation for ARN {arn}: {e}")
    except Exception as e:
        db.rollback()
        print(f"❌ Error while inserting/updating recommendation for ARN {arn}: {e}")
