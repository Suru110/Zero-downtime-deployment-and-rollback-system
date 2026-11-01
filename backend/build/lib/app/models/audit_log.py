import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, JSON, DateTime, ForeignKey, Index
from app.core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity_created", "entity_type", "entity_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    username = Column(String(50), nullable=True)
    
    action = Column(String(100), nullable=False)   # e.g. project.create, deployment.trigger, rollback.execute
    entity_type = Column(String(50), nullable=False) # project, environment, release, deployment, rollback
    entity_id = Column(String(36), nullable=False)
    
    ip_address = Column(String(50), nullable=True)
    details = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
