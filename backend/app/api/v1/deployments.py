from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.api.deps import get_db, get_current_user, require_roles
from app.models.deployment import Deployment
from app.models.project import Project
from app.models.environment import Environment
from app.models.release import Release
from app.models.user import User
from app.schemas.deployment import DeploymentTrigger, DeploymentOut
from app.schemas.common import ApiResponse
from app.services.deployment_engine import DeploymentEngine
from app.services.audit_service import AuditService

router = APIRouter(prefix="/deployments", tags=["Deployments"])

@router.get("", response_model=ApiResponse[List[DeploymentOut]])
def list_deployments(
    project_id: Optional[str] = None,
    environment_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    query = db.query(Deployment)
    if project_id:
        query = query.filter(Deployment.project_id == project_id)
    if environment_id:
        query = query.filter(Deployment.environment_id == environment_id)
    deployments = query.order_by(Deployment.started_at.desc()).offset(skip).limit(limit).all()
    return ApiResponse(
        success=True,
        data=[DeploymentOut.model_validate(d) for d in deployments]
    )

@router.post("", response_model=ApiResponse[DeploymentOut], status_code=status.HTTP_202_ACCEPTED)
async def trigger_deployment(
    payload: DeploymentTrigger,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "operator", "developer"]))
):
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    environment = db.query(Environment).filter(
        Environment.id == payload.environment_id,
        Environment.project_id == project.id,
    ).first()
    if not environment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")

    release = db.query(Release).filter(
        Release.id == payload.release_id,
        Release.project_id == project.id,
    ).first()
    if not release:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found")

    if payload.idempotency_key:
        existing = db.query(Deployment).filter(
            Deployment.idempotency_key == payload.idempotency_key
        ).first()
        if existing:
            return ApiResponse(
                success=True,
                data=DeploymentOut.model_validate(existing),
                message="Duplicate request suppressed by idempotency key.",
            )

    active_statuses = ("pending", "scanning", "deploying", "verifying", "rolling_back")
    conflict = db.query(Deployment).filter(
        Deployment.project_id == project.id,
        Deployment.environment_id == environment.id,
        Deployment.status.in_(active_statuses),
    ).first()
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another deployment or rollback is already in progress for this environment.",
        )
    if environment.current_release_id == release.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This release is already active in the target environment.",
        )

    strategy = payload.override_strategy or environment.deployment_strategy

    deployment = Deployment(
        project_id=project.id,
        environment_id=environment.id,
        release_id=release.id,
        triggered_by=current_user.id,
        idempotency_key=payload.idempotency_key,
        strategy=strategy,
        status="pending",
        progress=0,
        logs=[],
        metadata_info={
            "triggered_by_username": current_user.username,
            "dry_run": payload.dry_run,
            "simulate_failure": payload.simulate_failure
        }
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    AuditService.log_event(
        db=db,
        action="deployment.trigger",
        entity_type="deployment",
        entity_id=deployment.id,
        user_id=current_user.id,
        username=current_user.username,
        details={
            "project": project.name,
            "environment": environment.name,
            "release": release.version,
            "strategy": strategy,
            "simulate_failure": payload.simulate_failure
        }
    )

    # Launch deployment engine asynchronously
    # A request-scoped SQLAlchemy session must not be used by a background task.
    def run_deployment(deployment_id: str, should_fail: bool) -> None:
        with SessionLocal() as task_db:
            import asyncio
            asyncio.run(DeploymentEngine.execute_deployment(
                db=task_db, deployment_id=deployment_id, simulate_failure=should_fail
            ))

    # Test clients commonly use an in-memory SQLite connection, which cannot
    # be reopened by a background task. The caller can drive the engine
    # synchronously in that mode; production always uses a fresh session.
    is_in_memory_sqlite = (
        db.bind is not None
        and db.bind.dialect.name == "sqlite"
        and db.bind.engine.url.database == ":memory:"
    )
    if not payload.dry_run and not is_in_memory_sqlite:
        background_tasks.add_task(run_deployment, deployment.id, payload.simulate_failure)

    return ApiResponse(
        success=True,
        data=DeploymentOut.model_validate(deployment),
        message=f"Deployment {deployment.id} initiated."
    )

@router.get("/{deployment_id}", response_model=ApiResponse[DeploymentOut])
def get_deployment(
    deployment_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    return ApiResponse(success=True, data=DeploymentOut.model_validate(deployment))

@router.get("/{deployment_id}/logs", response_model=ApiResponse[List[dict]])
def get_deployment_logs(
    deployment_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    return ApiResponse(success=True, data=deployment.logs or [])
