from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_owned_deployment
from app.models.health_check import HealthCheck
from app.models.user import User
from app.schemas.health_check import HealthCheckOut
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/deployments/{deployment_id}/health-checks", tags=["Health Checks"])

@router.get("", response_model=ApiResponse[List[HealthCheckOut]])
def list_deployment_health_checks(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    deployment = get_owned_deployment(db, deployment_id, current_user)

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
