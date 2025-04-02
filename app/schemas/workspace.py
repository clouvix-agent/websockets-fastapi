from pydantic import BaseModel
from typing import Optional, Dict, Any

class WorkspaceBase(BaseModel):
    wsname: str
    filetype: str
    filelocation: Optional[str] = None
    diagramjson: Optional[Dict[str, Any]] = None

class WorkspaceCreate(WorkspaceBase):
    userid: int

class Workspace(WorkspaceBase):
    id: int
    userid: int

    class Config:
        from_attributes = True 