from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from fastapi.responses import JSONResponse
from app.auth.utils import SECRET_KEY, ALGORITHM
from app.database import get_db
from fastapi.security import OAuth2PasswordBearer
from app.db.drift import fetch_all_drifts_for_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter(
    prefix="/api/drift",
    tags=["drift"]
)


@router.get("/")
async def get_user_drifts(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        userid = payload.get("id")
        if not userid:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    drifts = fetch_all_drifts_for_user(db, userid)

    result = []
    for drift in drifts:
        result.append({
            "project_name": drift.project_name,
            "drift_reason": drift.drift_reason,
            "updated_time": drift.updated_time.isoformat()
        })

    return JSONResponse(content=result)
