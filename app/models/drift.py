from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from datetime import datetime
from app.database import Base
import pytz

IST = pytz.timezone("Asia/Kolkata")

class DriftDetection(Base):
    __tablename__ = "drift_detection"
    __table_args__ = (
        UniqueConstraint("userid", "project_name", name="uniq_user_project"),
    )

    id = Column(Integer, primary_key=True, index=True)
    userid = Column(Integer, nullable=False)
    project_name = Column(String, nullable=False)
    drift_reason = Column(Text, nullable=False)
    updated_time = Column(DateTime(timezone=True), default=lambda: datetime.now(IST), onupdate=lambda: datetime.now(IST))
