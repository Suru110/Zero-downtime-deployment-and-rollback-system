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
from app.models.rollback import RollbackEvent
from app.models.user import User
from app.schemas.deployment import DeploymentTrigger, DeploymentOut
from app.schemas.common import ApiResponse
from app.services.deployment_engine import DeploymentEngine
from app.services.audit_service import AuditService
from app.adapters import get_deployment_adapter
from app.core.kubernetes import normalize_kubernetes_name
from app.api.v1.releases import IMAGE_REFERENCE_PATTERN

router = APIRouter(prefix="/deployments", tags=["Deployments"])

TERMINAL_STATUSES = {"active", "rolled_back", "failed", "cancelled"}
DELETABLE_STATUSES = TERMINAL_STATUSES | {"pending"}
PAUSABLE_STATUSES = {"pending", "scanning", "deploying", "verifying"}

def _clear_current_release_if_deleted(
    db: Session,
    environment_id: str,
    release_id: str,
) -> None:
    db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.current_release_id == release_id,
    ).update(
        {Environment.current_release_id: None},
        synchronize_session=False,
    )

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

@router.delete("", response_model=ApiResponse[dict])
def delete_all_deployments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    deployments = (
        db.query(Deployment)
        .join(Project)
        .filter(Project.owner_id == current_user.id)
        .all()
    )
    active = [deployment for deployment in deployments if deployment.status not in DELETABLE_STATUSES]
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stop or finish all in-progress deployments before deleting deployment history.",
        )
    deployment_ids = [deployment.id for deployment in deployments]
    if deployment_ids:
        db.query(RollbackEvent).filter(
            RollbackEvent.source_deployment_id.in_(deployment_ids)
        ).delete(synchronize_session=False)
    for deployment in deployments:
        if deployment.status == "active":
            _clear_current_release_if_deleted(db, deployment.environment_id, deployment.release_id)
        db.delete(deployment)
    db.commit()
    return ApiResponse(
        success=True,
        data={"deleted": len(deployments)},
        message=f"Deleted {len(deployments)} deployment records.",
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
        active_release_deployment = db.query(Deployment.id).filter(
            Deployment.environment_id == environment.id,
            Deployment.release_id == release.id,
            Deployment.status == "active",
        ).first()
        if not active_release_deployment:
            _clear_current_release_if_deleted(db, environment.id, release.id)
            db.refresh(environment)
    if environment.current_release_id == release.id and not payload.redeploy:
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
            "redeploy": payload.redeploy,
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
            "redeploy": payload.redeploy,
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

@router.get("/{deployment_id}/endpoint", response_model=ApiResponse[DeploymentOut])
async def get_deployment_endpoint(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deployment = get_owned_deployment(db, deployment_id, current_user)
    project = db.query(Project).filter(Project.id == deployment.project_id).first()
    environment = db.query(Environment).filter(Environment.id == deployment.environment_id).first()
    if not project or not environment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment target not found.")

    adapter = get_deployment_adapter()
    endpoint = {
        "status": "unavailable",
        "error": "The configured adapter does not expose a reachable endpoint.",
    }
    discover_endpoint = getattr(adapter, "discover_service_endpoint", None)
    if callable(discover_endpoint):
        endpoint = await discover_endpoint(
            app_name=normalize_kubernetes_name(project.name),
            namespace=normalize_kubernetes_name(environment.k8s_namespace),
            port=project.default_port,
            health_path=project.health_path,
        )

    metadata = dict(deployment.metadata_info or {})
    metadata["endpoint_status"] = endpoint.get("status", "unavailable")
    if endpoint.get("public_url"):
        metadata["public_url"] = endpoint["public_url"]
        metadata.pop("endpoint_error", None)
    else:
        metadata.pop("public_url", None)
        metadata["endpoint_error"] = endpoint.get(
            "error", "No reachable endpoint has been assigned yet."
        )
    metadata["endpoint_details"] = {
        key: value for key, value in endpoint.items() if key != "public_url"
    }
    deployment.metadata_info = metadata
    db.commit()
    db.refresh(deployment)
    return ApiResponse(
        success=True,
        data=DeploymentOut.model_validate(deployment),
        message=(
            "Application endpoint is ready."
            if endpoint.get("public_url")
            else "Application endpoint is not ready yet."
        ),
    )

@router.delete("/{deployment_id}", response_model=ApiResponse[bool])
def delete_deployment(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    deployment = get_owned_deployment(db, deployment_id, current_user)
    if deployment.status not in DELETABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending or completed deployments can be deleted.",
        )
    db.query(RollbackEvent).filter(
        RollbackEvent.source_deployment_id == deployment.id
    ).delete(synchronize_session=False)
    if deployment.status == "active":
        _clear_current_release_if_deleted(db, deployment.environment_id, deployment.release_id)
    db.delete(deployment)
    db.commit()
    return ApiResponse(success=True, data=True, message="Deployment record deleted.")

@router.post("/{deployment_id}/pause", response_model=ApiResponse[DeploymentOut])
def pause_deployment(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deployment = get_owned_deployment(db, deployment_id, current_user)
    if deployment.status not in PAUSABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only in-progress deployments can be paused.",
        )
    metadata = dict(deployment.metadata_info or {})
    if metadata.get("paused"):
        return ApiResponse(success=True, data=DeploymentOut.model_validate(deployment), message="Deployment is already paused.")
    metadata["paused"] = True
    deployment.metadata_info = metadata
    logs = list(deployment.logs or [])
    logs.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": "WARN",
        "message": "Deployment paused by user. Resume it to continue the pipeline.",
    })
    deployment.logs = logs
    db.commit()
    db.refresh(deployment)
    return ApiResponse(success=True, data=DeploymentOut.model_validate(deployment), message="Deployment paused.")

@router.post("/{deployment_id}/resume", response_model=ApiResponse[DeploymentOut])
def resume_deployment(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deployment = get_owned_deployment(db, deployment_id, current_user)
    if deployment.status not in PAUSABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only in-progress deployments can be resumed.",
        )
    metadata = dict(deployment.metadata_info or {})
    if not metadata.get("paused"):
        return ApiResponse(success=True, data=DeploymentOut.model_validate(deployment), message="Deployment is not paused.")
    metadata["paused"] = False
    deployment.metadata_info = metadata
    logs = list(deployment.logs or [])
    logs.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": "INFO",
        "message": "Deployment resumed by user.",
    })
    deployment.logs = logs
    db.commit()
    db.refresh(deployment)
    return ApiResponse(success=True, data=DeploymentOut.model_validate(deployment), message="Deployment resumed.")

@router.get("/{deployment_id}/logs", response_model=ApiResponse[List[dict]])
def get_deployment_logs(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    deployment = get_owned_deployment(db, deployment_id, current_user)
    return ApiResponse(success=True, data=deployment.logs or [])
