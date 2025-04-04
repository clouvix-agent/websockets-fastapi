from sqlalchemy import Column, Integer, String, JSON, ForeignKey
from app.database import Base

class Workspace(Base):
    __tablename__ = "workspaces"

    wsid = Column(Integer, primary_key=True, index=True)
    userid = Column(Integer, ForeignKey("users.id"), nullable=False)
    wsname = Column(String, nullable=False)
    filetype = Column(String, nullable=False)
    filelocation = Column(String, nullable=True)
    diagramjson = Column(JSON, nullable=True) 
    githublocation = Column(String, nullable=True)