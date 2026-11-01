from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, require_roles
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectOut
from app.schemas.common import ApiResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.get("", response_model=ApiResponse[List[ProjectOut]])
def list_projects(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    query = db.query(Project)
    if search:
        query = query.filter(Project.name.ilike(f"%{search}%"))
    projects = query.offset(skip).limit(limit).all()
    return ApiResponse(
        success=True,
        data=[ProjectOut.model_validate(p) for p in projects]
    )

@router.post("", response_model=ApiResponse[ProjectOut], status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "operator", "developer"]))
):
    existing = db.query(Project).filter(Project.name == project_in.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project with name '{project_in.name}' already exists."
        )

    project = Project(
        **project_in.model_dump(),
        owner_id=current_user.id
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    AuditService.log_event(
        db=db,
        action="project.create",
        entity_type="project",
        entity_id=project.id,
        user_id=current_user.id,
        username=current_user.username,
        details={"name": project.name, "git_repo": project.git_repo}
    )

    return ApiResponse(success=True, data=ProjectOut.model_validate(project))

@router.get("/{project_id}", response_model=ApiResponse[ProjectOut])
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ApiResponse(success=True, data=ProjectOut.model_validate(project))

@router.put("/{project_id}", response_model=ApiResponse[ProjectOut])
def update_project(
    project_id: str,
    project_in: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "operator"]))
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    update_data = project_in.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(project, field, val)
    db.commit()
    db.refresh(project)

    AuditService.log_event(
        db=db,
        action="project.update",
        entity_type="project",
        entity_id=project.id,
        user_id=current_user.id,
        username=current_user.username,
        details=update_data
    )

    return ApiResponse(success=True, data=ProjectOut.model_validate(project))

@router.delete("/{project_id}", response_model=ApiResponse[bool])
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"]))
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    
    db.delete(project)
    db.commit()

    AuditService.log_event(
        db=db,
        action="project.delete",
        entity_type="project",
        entity_id=project_id,
        user_id=current_user.id,
        username=current_user.username,
        details={"name": project.name}
    )

    return ApiResponse(success=True, data=True, message=f"Project '{project.name}' deleted successfully.")
