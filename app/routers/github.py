import os
import time
import json
import jwt
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel

from jose import jwt as jose_jwt, JWTError
from app.database import get_db
from app.models.connection import Connection
from app.auth.utils import SECRET_KEY, ALGORITHM

from dotenv import load_dotenv
load_dotenv()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

router = APIRouter(
    prefix="/api/github",
    tags=["github"]
)

# --------------------------- GitHub App Client ---------------------------

class GitHubAppClient:
    def __init__(self, app_id, private_key, installation_id):
        self.app_id = app_id
        self.installation_id = installation_id
        
        # Format the private key if needed
        if private_key and "-----BEGIN RSA PRIVATE KEY-----" not in private_key:
            self.private_key = "-----BEGIN RSA PRIVATE KEY-----\n" + private_key.strip() + "\n-----END RSA PRIVATE KEY-----"
        else:
            self.private_key = private_key
            
        self.installation_token = None
        self.token_expires_at = None

    def _generate_jwt(self):
        now = int(time.time())
        payload = {
            'iat': now,
            'exp': now + 600,
            'iss': self.app_id
        }
        
        # Format the private key correctly if needed
        private_key = self.private_key
        
        # If the private key doesn't have the BEGIN/END headers, add them
        if "-----BEGIN RSA PRIVATE KEY-----" not in private_key:
            private_key = "-----BEGIN RSA PRIVATE KEY-----\n" + private_key.strip() + "\n-----END RSA PRIVATE KEY-----"
            
        return jwt.encode(payload, private_key, algorithm='RS256')

    def _get_installation_token(self):
        if self.installation_token and self.token_expires_at > datetime.now(timezone.utc):
            return self.installation_token

        jwt_token = self._generate_jwt()
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github.v3+json',
            'X-GitHub-Api-Version': '2022-11-28'
        }
        url = f'https://api.github.com/app/installations/{self.installation_id}/access_tokens'
        response = requests.post(url, headers=headers)
        response.raise_for_status()

        token_data = response.json()
        self.installation_token = token_data['token']
        self.token_expires_at = datetime.fromisoformat(token_data['expires_at'].replace('Z', '+00:00'))
        return self.installation_token

    def _make_authenticated_request(self, url, method='GET', **kwargs):
        token = self._get_installation_token()
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'X-GitHub-Api-Version': '2022-11-28'
        }
        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
        kwargs['headers'] = headers
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_installation_repositories(self):
        url = f'https://api.github.com/installation/repositories'
        all_repos = []
        page = 1
        while True:
            params = {'per_page': 100, 'page': page}
            data = self._make_authenticated_request(url, params=params)
            repositories = data.get('repositories', [])
            all_repos.extend(repositories)
            if len(repositories) < 100:
                break
            page += 1
        return all_repos

    def get_repository_names(self):
        repositories = self.get_installation_repositories()
        return [repo['name'] for repo in repositories]

# --------------------------- Utility to Get Installation ID ---------------------------

def get_github_installation_id(user_id: int):
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        if not DATABASE_URL:
            raise HTTPException(status_code=500, detail="DATABASE_URL not configured")

        engine = create_engine(DATABASE_URL)
        with engine.connect() as connection:
            query = text("""
                SELECT connection_json FROM connections
                WHERE userid = :user_id AND type = 'github';
            """)
            result = connection.execute(query, {"user_id": user_id})

            for row in result:
                # Handle the case where connection_json could be a string or already a list
                if isinstance(row.connection_json, str):
                    try:
                        json_data = json.loads(row.connection_json)
                    except json.JSONDecodeError:
                        print(f"Error decoding JSON: {row.connection_json}")
                        raise HTTPException(status_code=500, detail="Invalid JSON in connection_json")
                else:
                    # If it's already a list or dictionary, use it directly
                    json_data = row.connection_json
                
                # Process the data based on its type
                if isinstance(json_data, list):
                    for item in json_data:
                        if isinstance(item, dict) and item.get("key") == "GITHUB_INSTALL_ID":
                            return str(item.get("value"))
                elif isinstance(json_data, dict):
                    if "GITHUB_INSTALL_ID" in json_data:
                        return str(json_data["GITHUB_INSTALL_ID"])
                    
        raise HTTPException(status_code=404, detail="GitHub installation ID not found")

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

# --------------------------- Save GitHub Installation ---------------------------

class GitHubInstallationRequest(BaseModel):
    installation_id: str

@router.post("/installationid")
async def save_github_installation(
    request: GitHubInstallationRequest,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    try:
        existing_connection = db.query(Connection).filter(
            Connection.userid == user_id,
            Connection.type == "github"
        ).first()

        connection_data = [{"key": "GITHUB_INSTALL_ID", "value": request.installation_id}]

        if existing_connection:
            try:
                existing_json = json.loads(existing_connection.connection_json)
                if isinstance(existing_json, list):
                    install_id_exists = False
                    for item in existing_json:
                        if isinstance(item, dict) and item.get("key") == "GITHUB_INSTALL_ID":
                            item["value"] = request.installation_id
                            install_id_exists = True
                            break
                    if not install_id_exists:
                        existing_json.append({"key": "GITHUB_INSTALL_ID", "value": request.installation_id})
                else:
                    existing_json = [
                        {"key": "GITHUB_TOKEN", "value": existing_json.get("GITHUB_TOKEN", "")},
                        {"key": "GITHUB_INSTALL_ID", "value": request.installation_id}
                    ]
                existing_connection.connection_json = json.dumps(existing_json)
                db.commit()
                return {
                    "message": "GitHub installation ID saved successfully",
                    "connection_id": existing_connection.connid
                }
            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=f"Error updating GitHub installation: {str(e)}")
        else:
            new_connection = Connection(
                userid=user_id,
                type="github",
                connection_json=json.dumps(connection_data),
                connection_bucket_name="github"
            )
            db.add(new_connection)
            db.commit()
            db.refresh(new_connection)
            return {
                "message": "GitHub installation ID saved successfully",
                "connection_id": new_connection.connid
            }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error saving GitHub installation ID: {str(e)}")

# --------------------------- List GitHub Repositories ---------------------------

@router.get("/list-repo")
async def list_repositories(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> List[str]:
    try:
        payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: No user ID found")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    try:
        # Check for environment variables
        APP_ID = os.getenv('GITHUB_APP_ID')
        PRIVATE_KEY = os.getenv('GITHUB_PRIVATE_KEY')
        
        if not APP_ID:
            raise HTTPException(status_code=500, detail="GitHub App ID is not configured")
            
        if not PRIVATE_KEY:
            raise HTTPException(status_code=500, detail="GitHub Private Key is not configured")
        
        # Format the private key if needed
        if "-----BEGIN RSA PRIVATE KEY-----" not in PRIVATE_KEY:
            PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----\n" + PRIVATE_KEY.strip() + "\n-----END RSA PRIVATE KEY-----"
        
        try:
            installation_id = get_github_installation_id(user_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"GitHub installation ID not found: {str(e)}")
        
        try:
            client = GitHubAppClient(APP_ID, PRIVATE_KEY, installation_id)
            try:
                repository_names = client.get_repository_names()
                return repository_names
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error fetching repositories: {str(e)}")
        except Exception as e:
            if "Invalid GitHub installation ID" in str(e):
                raise HTTPException(status_code=401, detail="Your GitHub installation appears to be invalid or revoked. Please reinstall the GitHub App.")
            else:
                raise HTTPException(status_code=500, detail=f"Error initializing GitHub client: {str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching repositories: {str(e)}")
