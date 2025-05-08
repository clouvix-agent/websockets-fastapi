from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from app.auth.utils import SECRET_KEY, ALGORITHM
from app.database import get_db
from app.models.recommendation import Recommendation
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter(
    prefix="/api/recommendations",
    tags=["recommendations"]
)

@router.get("/")
async def get_recommendations(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        # Decode JWT token to extract user_id
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    try:
        # Query all recommendations for the logged-in user
        recommendations = db.query(Recommendation).filter(
            Recommendation.userid == user_id
        ).all()

        if not recommendations:
            return {"message": "No recommendations found for this user", "recommendations": []}

        # Format response
        return {
            "recommendations": [
                {
                    "resource_type": rec.resource_type,
                    "arn": rec.arn,
                    "recommendation_text": rec.recommendation_text,
                    "updated_timestamp": rec.updated_timestamp
                }
                for rec in recommendations
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recommendations: {str(e)}")