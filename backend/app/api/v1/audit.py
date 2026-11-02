from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogOut
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])

@router.get("", response_model=ApiResponse[List[AuditLogOut]])
def list_audit_logs(
    entity_type: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(AuditLog).filter(AuditLog.user_id == current_user.id)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    logs = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    return ApiResponse(
        success=True,
        data=[AuditLogOut.model_validate(l) for l in logs]
    )
