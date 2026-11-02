from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_owned_deployment
from app.models.deployment import Deployment
from app.models.project import Project
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
    current_user: User = Depends(get_current_user)
):
    query = (
        db.query(RollbackEvent)
        .join(Deployment, Deployment.id == RollbackEvent.source_deployment_id)
        .join(Project, Project.id == Deployment.project_id)
        .filter(Project.owner_id == current_user.id)
    )
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
    current_user: User = Depends(get_current_user)
):
    deployment = get_owned_deployment(db, payload.deployment_id, current_user)
    if deployment.status in {"rolling_back", "rolled_back"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A rollback is already in progress or completed")

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
