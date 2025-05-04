from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, func
from app.database import Base

class InfrastructureInventory(Base):
    __tablename__ = "infrastructure_inventory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_name = Column(String(255), nullable=False)
    resource_type = Column(String(100), nullable=False)  # e.g., EC2, S3
    resource_name = Column(String(255), nullable=False)  # Terraform logical name
    arn = Column(String, nullable=False, index=True)
    terraform_type = Column(String(100), nullable=False)  # e.g., aws_instance
    resource_identifier = Column(String(255), nullable=True)
    attributes = Column(JSON, nullable=False)  # Full attributes block
    dependencies = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
