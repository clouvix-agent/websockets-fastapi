from sqlalchemy import Boolean, Column, String, Integer
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    organization = Column(String, nullable=False)
    disabled = Column(Boolean, default=False)
    verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    otp = Column(String, nullable=True)  
    otp_valid_until = Column(String, nullable=True)  