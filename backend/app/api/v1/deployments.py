from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.api.deps import get_db, get_current_user, get_owned_deployment, get_owned_project
from app.models.deployment import Deployment
from app.models.project import Project
from app.models.environment import Environment
from app.models.release import Release
from app.models.user import User
from app.schemas.deployment import DeploymentTrigger, DeploymentOut
from app.schemas.common import ApiResponse
from app.services.deployment_engine import DeploymentEngine
from app.services.audit_service import AuditService
from app.api.v1.releases import IMAGE_REFERENCE_PATTERN

router = APIRouter(prefix="/deployments", tags=["Deployments"])

@router.get("", response_model=ApiResponse[List[DeploymentOut]])
def list_deployments(
    project_id: Optional[str] = None,
    environment_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Deployment).join(Project).filter(Project.owner_id == current_user.id)
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
    current_user: User = Depends(get_current_user)
):
    project = get_owned_project(db, payload.project_id, current_user)

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
    if release.build_status != "published" or not release.image_reference:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected release is not published and cannot be deployed.",
        )
    if not IMAGE_REFERENCE_PATTERN.fullmatch(release.image_reference):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The selected release has an invalid image reference.",
        )

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
    if strategy not in {"rolling", "canary"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Deployment strategy must be rolling or canary.",
        )

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
            try:
                asyncio.run(DeploymentEngine.execute_deployment(
                    db=task_db, deployment_id=deployment_id, simulate_failure=should_fail
                ))
            except Exception as exc:
                deployment = task_db.query(Deployment).filter(
                    Deployment.id == deployment_id
                ).first()
                if deployment and deployment.status not in {"active", "rolled_back", "failed", "cancelled"}:
                    logs = list(deployment.logs or [])
                    logs.append({
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "level": "ERROR",
                        "message": f"Deployment execution stopped unexpectedly: {exc}",
                    })
                    deployment.status = "failed"
                    deployment.finished_at = datetime.utcnow()
                    deployment.logs = logs
                    task_db.commit()
                raise

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
    current_user: User = Depends(get_current_user)
):
    deployment = get_owned_deployment(db, deployment_id, current_user)
    return ApiResponse(success=True, data=DeploymentOut.model_validate(deployment))

@router.get("/{deployment_id}/logs", response_model=ApiResponse[List[dict]])
def get_deployment_logs(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    deployment = get_owned_deployment(db, deployment_id, current_user)
    return ApiResponse(success=True, data=deployment.logs or [])
