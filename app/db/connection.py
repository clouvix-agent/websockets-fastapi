from sqlalchemy.orm import Session
from app.models.connection import Connection
from app.schemas.connection import ConnectionCreate

def create_connection(db: Session, connection: ConnectionCreate) -> Connection:
    """
    Create a new connection in the database.
    
    Args:
        db: Database session
        connection: Connection data to be inserted
        
    Returns:
        Created connection object
    """
    db_connection = Connection(**connection.model_dump())
    db.add(db_connection)
    db.commit()
    db.refresh(db_connection)
    return db_connection

def get_connection(db: Session, conn_id: int) -> Connection:
    """
    Get a connection by its connection ID.
    
    Args:
        db: Database session
        conn_id: ID of the connection to retrieve
        
    Returns:
        Connection object if found, None otherwise
    """
    return db.query(Connection).filter(Connection.connid == conn_id).first()

def get_user_connections(db: Session, user_id: int) -> list[Connection]:
    """
    Get all connections for a specific user.
    
    Args:
        db: Database session
        user_id: ID of the user
        
    Returns:
        List of connections belonging to the user
    """
    return db.query(Connection).filter(Connection.userid == user_id).all()

def get_user_connections_by_type(db: Session, user_id: int, conn_type: str) -> list[Connection]:
    """
    Get all connections of a specific type (e.g., 'aws', 'gcp') for a user.
    
    Args:
        db: Database session
        user_id: ID of the user
        conn_type: Type of connection
        
    Returns:
        List of matching connections
    """
    return db.query(Connection).filter(Connection.userid == user_id, Connection.type == conn_type).all()
