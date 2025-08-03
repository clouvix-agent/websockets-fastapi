from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint , JSON
from sqlalchemy.sql import func
from app.database import Base

class Recommendation(Base):
    __tablename__ = "recommendation"

    id = Column(Integer, primary_key=True, index=True)
    userid = Column(Integer, nullable=False)
    resource_type = Column(String(50), nullable=False)
    arn = Column(Text, nullable=False)
    recommendation_text = Column(Text, nullable=False)
    updated_timestamp = Column(DateTime, nullable=True, server_default=func.current_timestamp())


    action = Column(JSON, nullable=True)
    impact = Column(JSON, nullable=True)
    savings = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("userid", "resource_type", "arn", name="unique_userid_resource_type_arn"),
    )