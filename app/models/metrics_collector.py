from sqlalchemy import Column, Integer, String, DateTime, JSON, func
from app.database import Base
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

def get_ist_time():
    return datetime.now(IST)

class MetricsCollection(Base):
    __tablename__ = "metrics_collection"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    userid = Column(Integer, nullable=False)
    arn = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=get_ist_time)
    updated_at = Column(DateTime(timezone=True), default=get_ist_time, onupdate=get_ist_time)
    resource_type = Column(String(100), nullable=False)
    metrics_data = Column(JSON, nullable=False)
    additional_info = Column(JSON, nullable=True)  
