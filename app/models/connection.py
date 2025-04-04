from sqlalchemy import Column, Integer, String, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Connection(Base):
    __tablename__ = "connections"

    connid = Column(Integer, primary_key=True, index=True)
    userid = Column(Integer)
    type = Column(String)
    connection_json = Column(JSON)
    connection_bucket_name = Column(String) 