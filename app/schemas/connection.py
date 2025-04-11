from pydantic import BaseModel
from typing import Optional, Dict, Any

class ConnectionBase(BaseModel):
    type: str
    connection_json: Dict[str, Any]
    connection_bucket_name: Optional[str] = None

class ConnectionCreate(ConnectionBase):
    userid: int

class Connection(ConnectionBase):
    connid: int
    userid: int

    class Config:
        from_attributes = True  # Enables ORM-to-schema conversion
