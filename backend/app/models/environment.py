import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, JSON, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base

class Environment(Base):
    __tablename__ = "environments"
    __table_args__ = (
        Index("ix_environments_project_name", "project_id", "name", unique=True),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    name = Column(String(50), nullable=False)  # dev, staging, production
    k8s_namespace = Column(String(100), nullable=False)
    k8s_cluster = Column(String(100), default="default", nullable=False)
    replicas = Column(Integer, default=2, nullable=False)
    deployment_strategy = Column(String(30), default="rolling", nullable=False)  # rolling, canary
    canary_steps = Column(JSON, default=lambda: [10, 25, 50, 100], nullable=False)
    auto_rollback_enabled = Column(Boolean, default=True, nullable=False)
    verification_timeout_seconds = Column(Integer, default=60, nullable=False)
    verification_attempts = Column(Integer, default=3, nullable=False)
    smoke_test_endpoint = Column(String(200), default="/healthz", nullable=False)
    smoke_test_expected_status = Column(Integer, default=200, nullable=False)
    smoke_test_timeout_seconds = Column(Integer, default=5, nullable=False)
    env_vars = Column(JSON, default=dict, nullable=False)
    
    # Tracks currently active release deployed to this environment
    current_release_id = Column(String(36), ForeignKey("releases.id", use_alter=True, name="fk_env_current_release"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="environments")
    deployments = relationship("Deployment", back_populates="environment", cascade="all, delete-orphan")
    current_release = relationship("Release", foreign_keys=[current_release_id])
