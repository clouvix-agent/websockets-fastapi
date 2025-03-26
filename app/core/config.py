from typing import List

class Settings():
    PROJECT_NAME: str = "Clouvix"
    ALLOWED_ORIGINS: List[str] = [
        "https://architecture.clouvix.com",
        "http://architecture.clouvix.com",
        "http://localhost:3000",
        "https://app.clouvix.com",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173"
    ]
    API_V1_STR: str = "/api/v1"
    
    # CORS Configuration
    ALLOW_CREDENTIALS: bool = True
    ALLOW_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    ALLOW_HEADERS: List[str] = ["*"]

    class Config:
        case_sensitive = True

settings = Settings() 