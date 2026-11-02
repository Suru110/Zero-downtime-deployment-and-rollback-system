import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, JSON, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base

class HealthCheck(Base):
    __tablename__ = "health_checks"
    __table_args__ = (Index("ix_health_checks_deployment_executed", "deployment_id", "executed_at"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deployment_id = Column(String(36), ForeignKey("deployments.id"), nullable=False)
    
    check_type = Column(String(50), nullable=False)  # readiness_probe, smoke_test, metric_error_rate
    status = Column(String(30), nullable=False)      # passed, failed, warning
    
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)
    details = Column(JSON, default=dict, nullable=False)
    
    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    deployment = relationship("Deployment", back_populates="health_checks")
