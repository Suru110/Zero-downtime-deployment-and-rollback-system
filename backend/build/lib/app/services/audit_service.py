from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from app.core.logging import get_logger

logger = get_logger("releasepilot.audit")

class AuditService:
    @staticmethod
    def log_event(
        db: Session,
        action: str,
        entity_type: str,
        entity_id: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """Create an immutable audit log entry."""
        audit_entry = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=ip_address,
            details=details or {}
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)
        
        logger.info(
            f"AUDIT: action={action} entity={entity_type}:{entity_id} actor={username or 'system'}"
        )
        return audit_entry
