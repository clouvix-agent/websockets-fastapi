from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class WorkspaceStatus(Base):
    __tablename__ = "workspace_status"

    id = Column(Integer, primary_key=True, index=True)
    userid = Column(Integer, nullable=False)
    project_name = Column(String(255), nullable=False)
    status = Column(Text, nullable=True)