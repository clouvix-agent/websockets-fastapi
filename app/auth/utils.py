from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
import random
import string
from decouple import config
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# JWT Configuration
SECRET_KEY = config("SECRET_KEY", default="your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Email configuration
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587)
EMAIL_USERNAME = config("EMAIL_USERNAME")
EMAIL_PASSWORD = config("EMAIL_PASSWORD")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))

def send_email(to_email: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_verification_email(email: str, otp: str) -> bool:
    subject = "Email Verification"
    body = f"""
    Welcome to Clouvix!
    Your verification code is: {otp}
    This code will expire in 10 minutes.
    """
    return send_email(email, subject, body)

def send_login_otp(email: str, otp: str) -> bool:
    subject = "Login OTP"
    body = f"""
    Your login OTP is: {otp}
    This code will expire in 5 minutes.
    """
    return send_email(email, subject, body)

def send_password_reset_email(email: str, reset_token: str) -> bool:
    subject = "Password Reset Request"
    body = f"""
    You have requested to reset your password.
    
    To reset your password, use this token: {reset_token}
    This token will expire in 10 minutes.
    
    If you did not request this password reset, please ignore this email.
    """
    return send_email(email, subject, body) 


