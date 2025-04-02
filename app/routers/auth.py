from datetime import datetime, timedelta
import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, OTPVerify, OTPLogin, Token, User as UserSchema, PasswordResetRequest, PasswordReset, PasswordResetResponse, MessageResponse
from app.auth.utils import (
    verify_password, get_password_hash, create_access_token,
    generate_otp, send_verification_email, send_login_otp,
    send_password_reset_email
)
from app.auth.deps import get_current_active_user
from jose import jwt
from jose.exceptions import JWTError

router = APIRouter(tags=["auth"])

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

@router.post("/register", response_model=UserSchema)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        name=user.name,
        organization=user.organization,
        password=hashed_password,
        otp=generate_otp(),
        otp_valid_until=(datetime.utcnow() + timedelta(minutes=10)).isoformat()
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    send_verification_email(db_user.email, db_user.otp)
    
    return db_user

@router.post("/verify-email", response_model=UserSchema)
async def verify_email(verify_data: OTPVerify, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == verify_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    if user.otp != verify_data.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP"
        )
    
    if datetime.utcnow() > datetime.fromisoformat(user.otp_valid_until):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired"
        )
    
    user.verified = True
    user.otp = None
    user.otp_valid_until = None
    db.commit()
    db.refresh(user)
    
    return user

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    if not verify_password(user_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    if not user.verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not verified"
        )
    
    access_token = create_access_token(data={    "sub": user.username,
    "id": user.id,
    "email": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login/otp", response_model=MessageResponse)
async def login_with_otp(login_data: OTPLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not verified"
        )
    
    otp = generate_otp()
    user.otp = otp
    user.otp_valid_until = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
    db.commit()
    
    send_login_otp(user.email, otp)
    
    
    return {"message": "OTP sent to your email"}

@router.post("/verify-login-otp", response_model=Token)
async def verify_login_otp(verify_data: OTPVerify, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == verify_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.otp != verify_data.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP"
        )
    
    if datetime.utcnow() > datetime.fromisoformat(user.otp_valid_until):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired"
        )
    
    user.otp = None
    user.otp_valid_until = None
    db.commit()
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/users/me", response_model=UserSchema)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

@router.post("/forget-password", response_model=PasswordResetResponse)
async def forget_password(request: PasswordResetRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Generate a reset token
    reset_token = create_access_token(
        data={"sub": user.username, "type": "password_reset"},
        expires_delta=timedelta(minutes=10)
    )
    
    # Store the reset token in the user's OTP field
    user.otp = reset_token
    user.otp_valid_until = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    db.commit()
    
    # Send reset email
    if not send_password_reset_email(user.email, reset_token):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send reset email"
        )
    
    return {"message": "Password reset instructions sent to your email", "token_type": "reset"}

@router.post("/reset-password", response_model=PasswordResetResponse)
async def reset_password(reset_data: PasswordReset, db: Session = Depends(get_db)):
    try:
        # Verify the reset token
        payload = jwt.decode(reset_data.token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reset token"
            )
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reset token"
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Get the user
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify that this is the latest reset token
    if user.otp != reset_data.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Check if the token has expired
    if datetime.utcnow() > datetime.fromisoformat(user.otp_valid_until):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired"
        )
    
    # Update the password
    user.password = get_password_hash(reset_data.new_password)
    user.otp = None
    user.otp_valid_until = None
    db.commit()
    
    return {"message": "Password reset successful", "token_type": "reset"} 