from pydantic import BaseModel, EmailStr
from typing import Optional

class UserBase(BaseModel):
    username: str
    email: EmailStr
    name: Optional[str] = None
    organization: str

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class OTPVerify(BaseModel):
    email: EmailStr
    otp: str

class OTPLogin(BaseModel):
    email: EmailStr

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    token: str
    new_password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class PasswordResetResponse(BaseModel):
    message: str
    token_type: str = "reset"
    
class MessageResponse(BaseModel):
    message: str

class User(UserBase):
    id: int
    disabled: bool
    verified: bool
    is_admin: bool

    class Config:
        from_attributes = True 