from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_owned_project
from app.models.environment import Environment
from app.models.user import User
from app.schemas.environment import EnvironmentCreate, EnvironmentUpdate, EnvironmentOut
from app.schemas.common import ApiResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/projects/{project_id}/environments", tags=["Environments"])

@router.get("", response_model=ApiResponse[List[EnvironmentOut]])
def list_environments(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = get_owned_project(db, project_id, current_user)
    
    envs = db.query(Environment).filter(Environment.project_id == project_id).all()
    return ApiResponse(
        success=True,
        data=[EnvironmentOut.model_validate(e) for e in envs]
    )

@router.post("", response_model=ApiResponse[EnvironmentOut], status_code=status.HTTP_201_CREATED)
def create_environment(
    project_id: str,
    env_in: EnvironmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = get_owned_project(db, project_id, current_user)

    existing = db.query(Environment).filter(
        Environment.project_id == project_id,
        Environment.name == env_in.name
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Environment '{env_in.name}' already exists for this project."
        )

    env = Environment(
        **env_in.model_dump(),
        project_id=project_id
    )
    db.add(env)
    db.commit()
    db.refresh(env)

    AuditService.log_event(
        db=db,
        action="environment.create",
        entity_type="environment",
        entity_id=env.id,
        user_id=current_user.id,
        username=current_user.username,
        details={"name": env.name, "namespace": env.k8s_namespace, "project": project.name}
    )

    return ApiResponse(success=True, data=EnvironmentOut.model_validate(env))

@router.put("/{environment_id}", response_model=ApiResponse[EnvironmentOut])
def update_environment(
    project_id: str,
    environment_id: str,
    env_in: EnvironmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    env = db.query(Environment).filter(
        Environment.id == environment_id,
        Environment.project_id == project_id
    ).first()
    if not env or env.project.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found")

    update_data = env_in.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(env, field, val)
    db.commit()
    db.refresh(env)

    AuditService.log_event(
        db=db,
        action="environment.update",
        entity_type="environment",
        entity_id=env.id,
        user_id=current_user.id,
        username=current_user.username,
        details=update_data
    )

    return ApiResponse(success=True, data=EnvironmentOut.model_validate(env))
