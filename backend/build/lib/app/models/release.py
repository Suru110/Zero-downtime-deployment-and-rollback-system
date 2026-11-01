import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, JSON, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base

class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (
        Index("ix_releases_project_version", "project_id", "version", unique=True),
        Index("ix_releases_project_created", "project_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    version = Column(String(50), nullable=False)  # e.g. v1.2.0
    git_commit = Column(String(40), nullable=False)
    git_branch = Column(String(100), default="main", nullable=False)
    image_tag = Column(String(100), nullable=False)
    commit_message = Column(Text, nullable=True)
    changelog = Column(Text, nullable=True)
    
    # Trivy scan summary
    scan_status = Column(String(30), default="unscanned", nullable=False)  # unscanned, clean, warning, critical
    scan_results = Column(JSON, default=dict, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="releases")
    deployments = relationship("Deployment", back_populates="release", foreign_keys="Deployment.release_id")
