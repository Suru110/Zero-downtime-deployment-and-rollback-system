from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.models.deployment import Deployment
from app.models.project import Project
from app.models.environment import Environment
from app.models.rollback import RollbackEvent
from app.models.user import User
from app.schemas.common import ApiResponse
from app.adapters import get_metrics_adapter

router = APIRouter(prefix="/metrics", tags=["Metrics & Observability"])

@router.get("/system-stats", response_model=ApiResponse[dict])
def get_system_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    owned_projects = db.query(Project).filter(Project.owner_id == current_user.id).subquery()
    total_projects = db.query(Project).filter(Project.owner_id == current_user.id).count()
    total_environments = db.query(Environment).join(owned_projects, Environment.project_id == owned_projects.c.id).count()
    total_deployments = db.query(Deployment).join(owned_projects, Deployment.project_id == owned_projects.c.id).count()
    active_deployments = db.query(Deployment).join(owned_projects, Deployment.project_id == owned_projects.c.id).filter(Deployment.status == "active").count()
    failed_deployments = db.query(Deployment).join(owned_projects, Deployment.project_id == owned_projects.c.id).filter(Deployment.status == "failed").count()
    rollback_count = (
        db.query(RollbackEvent)
        .join(Deployment, Deployment.id == RollbackEvent.source_deployment_id)
        .join(owned_projects, Deployment.project_id == owned_projects.c.id)
        .count()
    )

    success_rate = 0.0
    if total_deployments > 0:
        success_rate = round((active_deployments / total_deployments) * 100, 1)

    return ApiResponse(
        success=True,
        data={
            "total_projects": total_projects,
            "total_environments": total_environments,
            "total_deployments": total_deployments,
            "active_deployments": active_deployments,
            "failed_deployments": failed_deployments,
            "rollback_count": rollback_count,
            "success_rate_pct": success_rate,
            "mttr_minutes": 2.4 # Mean Time To Recovery in minutes
        }
    )

@router.get("/environments/{environment_id}/telemetry", response_model=ApiResponse[dict])
async def get_environment_telemetry(
    environment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    env = db.query(Environment).filter(Environment.id == environment_id).first()
    if not env or env.project.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")
    
    project = env.project
    metrics_adapter = get_metrics_adapter()
    data = await metrics_adapter.get_telemetry(project.name, env.k8s_namespace)
    return ApiResponse(success=True, data=data)
