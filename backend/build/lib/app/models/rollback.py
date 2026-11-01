import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, JSON, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base

class RollbackEvent(Base):
    __tablename__ = "rollback_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_deployment_id = Column(String(36), ForeignKey("deployments.id"), nullable=False)
    environment_id = Column(String(36), ForeignKey("environments.id"), nullable=False)
    
    # Releases involved
    failed_release_id = Column(String(36), ForeignKey("releases.id"), nullable=False)
    restored_release_id = Column(String(36), ForeignKey("releases.id"), nullable=False)
    
    is_automated = Column(Boolean, default=True, nullable=False)
    triggered_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    reason = Column(Text, nullable=False)
    status = Column(String(30), default="completed", nullable=False)  # in_progress, completed, failed
    details = Column(JSON, default=dict, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    deployment = relationship("Deployment", back_populates="rollback_events", foreign_keys=[source_deployment_id])
    failed_release = relationship("Release", foreign_keys=[failed_release_id])
    restored_release = relationship("Release", foreign_keys=[restored_release_id])
