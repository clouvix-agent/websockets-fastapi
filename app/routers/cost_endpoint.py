from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from app.auth.utils import SECRET_KEY, ALGORITHM
from app.database import get_db
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter(
    prefix="/api/cost",
    tags=["cost"]
)

@router.get("")
async def get_all_cost(
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
        # Aggregated cost per product for the logged-in user (all services)
        result = db.execute(text("""
            SELECT
                p.product_name,
                SUM((item_details.value->>'total_cost')::numeric) AS total_aggregated_cost
            FROM
                cur_report AS p,
                jsonb_array_elements(p.report_json->'details') AS item_details 
            WHERE
                p.userid = :user_id
                AND p.report_json IS NOT NULL
                AND p.report_json->'details' IS NOT NULL 
                AND jsonb_typeof(p.report_json->'details') = 'array' 
            GROUP BY
                p.product_name
            ORDER BY
                p.product_name;
        """), {"user_id": str(user_id)})
        rows = result.fetchall()

        if not rows:
            return {"message": "No cost data found for this user", "cost": []}

        # Format response for all services
        return {
            "cost": [
                {
                    "product_name": row.product_name,
                    "total_aggregated_cost": float(row.total_aggregated_cost)
                }
                for row in rows
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching all cost data: {str(e)}")

@router.get("/{service_name}")
async def get_cost_by_service(
    service_name: str,  # Dynamic parameter for the service/product name
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
        # Dynamically generate the SQL query based on the service_name
        query = f"""
            SELECT
                p.usage_date,
                p.product_name,
                item_details.value->>'arn' AS arn,
                SUM((item_details.value->>'total_usage')::numeric) AS total_usage,
                SUM((item_details.value->>'total_cost')::numeric) AS total_cost
            FROM
                cur_report AS p,
                jsonb_array_elements(p.report_json->'details') AS item_details 
            WHERE
                p.userid = :user_id
                AND p.product_name = :service_name
                AND p.report_json IS NOT NULL
                AND p.report_json->'details' IS NOT NULL 
                AND jsonb_typeof(p.report_json->'details') = 'array' 
            GROUP BY
                p.usage_date, p.product_name, arn
            ORDER BY
                p.usage_date;
        """

        # Execute the query with dynamic service_name
        result = db.execute(text(query), {"user_id": str(user_id), "service_name": service_name})
        rows = result.fetchall()

        if not rows:
            return {"message": f"No cost data found for the service '{service_name}' for this user", "cost": []}

        # Format response for the specified service
        return {
            "cost": [
                {
                    "usage_date": row.usage_date,
                    "arn": row.arn,
                    "total_usage": float(row.total_usage),
                    "total_cost": float(row.total_cost)
                }
                for row in rows
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching cost data for {service_name}: {str(e)}")
