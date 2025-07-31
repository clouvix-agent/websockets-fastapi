from app.database import engine
from app.models.metrics_collector import MetricsCollection
from app.database import Base

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Table created successfully.")
