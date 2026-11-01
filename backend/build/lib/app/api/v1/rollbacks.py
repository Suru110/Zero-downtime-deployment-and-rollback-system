from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, require_roles
from app.models.deployment import Deployment
from app.models.rollback import RollbackEvent
from app.models.user import User
from app.schemas.rollback import RollbackTrigger, RollbackEventOut
from app.schemas.common import ApiResponse
from app.services.rollback_manager import RollbackManager

router = APIRouter(prefix="/rollbacks", tags=["Rollbacks"])

@router.get("", response_model=ApiResponse[List[RollbackEventOut]])
def list_rollbacks(
    environment_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    query = db.query(RollbackEvent)
    if environment_id:
        query = query.filter(RollbackEvent.environment_id == environment_id)
    rollbacks = query.order_by(RollbackEvent.created_at.desc()).offset(skip).limit(limit).all()
    return ApiResponse(
        success=True,
        data=[RollbackEventOut.model_validate(r) for r in rollbacks]
    )

@router.post("", response_model=ApiResponse[RollbackEventOut])
async def trigger_manual_rollback(
    payload: RollbackTrigger,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "operator"]))
):
    deployment = db.query(Deployment).filter(Deployment.id == payload.deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")

    try:
        rollback_event = await RollbackManager.trigger_rollback(
            db=db,
            deployment=deployment,
            reason=payload.reason,
            is_automated=False,
            triggered_by_user_id=current_user.id,
            username=current_user.username
        )
        return ApiResponse(
            success=True,
            data=RollbackEventOut.model_validate(rollback_event),
            message="Rollback triggered and completed successfully."
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
