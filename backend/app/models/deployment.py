import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, JSON, DateTime, ForeignKey, Integer, Index
from sqlalchemy.orm import relationship
from app.core.database import Base

class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (
        Index("ix_deployments_environment_started", "environment_id", "started_at"),
        Index("ix_deployments_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    environment_id = Column(String(36), ForeignKey("environments.id"), nullable=False)
    release_id = Column(String(36), ForeignKey("releases.id"), nullable=False)
    triggered_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    idempotency_key = Column(String(128), nullable=True, unique=True, index=True)

    # Status: pending, scanning, deploying, verifying, active, failed, rolled_back, cancelled
    status = Column(String(30), default="pending", nullable=False)
    strategy = Column(String(30), default="rolling", nullable=False)
    
    # Progress: 0 - 100%
    progress = Column(Integer, default=0, nullable=False)
    
    # Execution adapter info
    is_simulated = Column(Boolean, default=False, nullable=False)
    adapter_name = Column(String(50), default="k8s-rolling", nullable=False)
    
    # Logs and details
    logs = Column(JSON, default=list, nullable=False)
    metadata_info = Column(JSON, default=dict, nullable=False)
    
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="deployments")
    environment = relationship("Environment", back_populates="deployments")
    release = relationship("Release", back_populates="deployments", foreign_keys=[release_id])
    health_checks = relationship("HealthCheck", back_populates="deployment", cascade="all, delete-orphan")
    rollback_events = relationship("RollbackEvent", back_populates="deployment", foreign_keys="RollbackEvent.source_deployment_id")
