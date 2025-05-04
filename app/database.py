from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from decouple import config

# Load the DATABASE_URL from environment variables
SQLALCHEMY_DATABASE_URL = config('DATABASE_URL')

# Create the SQLAlchemy engine with better connection handling
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,       # Detect and refresh dead connections
    pool_size=10,             # Base number of DB connections to keep
    max_overflow=20           # Allow 20 extra temporary connections if pool is exhausted
)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create the declarative base for models
Base = declarative_base()

# For FastAPI dependency injection
def get_db():
    """
    Standard generator for FastAPI.
    Usage: Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Context manager for non-FastAPI use (especially inside tools and agents)
@contextmanager
def get_db_session():
    """
    Context manager for using database sessions safely outside FastAPI.
    Usage: with get_db_session() as db:
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
