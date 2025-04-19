from pydantic import BaseModel

class WorkspaceStatusCreate(BaseModel):
    userid: int
    project_name: str
    status: str

class WorkspaceStatusOut(WorkspaceStatusCreate):
    id: int

    class Config:
        orm_mode = True
