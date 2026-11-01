from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.models.deployment import Deployment
from app.models.health_check import HealthCheck
from app.models.user import User
from app.schemas.health_check import HealthCheckOut
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/deployments/{deployment_id}/health-checks", tags=["Health Checks"])

@router.get("", response_model=ApiResponse[List[HealthCheckOut]])
def list_deployment_health_checks(
    deployment_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")

    checks = (
        db.query(HealthCheck)
        .filter(HealthCheck.deployment_id == deployment_id)
        .order_by(HealthCheck.executed_at.asc())
        .all()
    )
    return ApiResponse(
        success=True,
        data=[HealthCheckOut.model_validate(c) for c in checks]
    )
