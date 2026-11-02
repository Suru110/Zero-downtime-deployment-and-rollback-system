from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user, get_owned_project
from app.models.project import Project
from app.models.release import Release
from app.models.user import User
from app.schemas.release import ReleaseCreate, ReleaseOut, ScanReport
from app.schemas.common import ApiResponse
from app.adapters import get_security_scanner_adapter
from app.services.audit_service import AuditService
import re

router = APIRouter(prefix="/projects/{project_id}/releases", tags=["Releases"])

IMAGE_REFERENCE_PATTERN = re.compile(
    r"^(?:[a-z0-9.-]+(?::[0-9]+)?/)?[a-z0-9._/-]+:[a-zA-Z0-9][a-zA-Z0-9._-]*$"
)

@router.get("", response_model=ApiResponse[List[ReleaseOut]])
def list_releases(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = get_owned_project(db, project_id, current_user)

    releases = (
        db.query(Release)
        .filter(Release.project_id == project_id)
        .order_by(Release.created_at.desc())
        .all()
    )
    return ApiResponse(
        success=True,
        data=[ReleaseOut.model_validate(r) for r in releases]
    )

@router.post("", response_model=ApiResponse[ReleaseOut], status_code=status.HTTP_201_CREATED)
def create_release(
    project_id: str,
    rel_in: ReleaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = get_owned_project(db, project_id, current_user)

    existing = db.query(Release).filter(
        Release.project_id == project_id,
        Release.version == rel_in.version
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Release version '{rel_in.version}' already registered for this project."
        )

    image_reference = rel_in.image_reference or f"{project.image_repository}:{rel_in.image_tag}"
    if not IMAGE_REFERENCE_PATTERN.fullmatch(image_reference):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The release image reference must include a repository and tag.",
        )

    release = Release(
        **rel_in.model_dump(exclude={"image_reference"}),
        project_id=project_id,
        image_reference=image_reference,
        build_status="published",
    )
    db.add(release)
    db.commit()
    db.refresh(release)

    AuditService.log_event(
        db=db,
        action="release.create",
        entity_type="release",
        entity_id=release.id,
        user_id=current_user.id,
        username=current_user.username,
        details={"version": release.version, "image_tag": release.image_tag, "project": project.name}
    )

    return ApiResponse(success=True, data=ReleaseOut.model_validate(release))

@router.post("/{release_id}/scan", response_model=ApiResponse[ScanReport])
async def scan_release(
    project_id: str,
    release_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    release = db.query(Release).filter(
        Release.id == release_id,
        Release.project_id == project_id
    ).first()
    if not release or release.project.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found")

    project = release.project
    scanner = get_security_scanner_adapter()
    full_image_ref = release.image_reference or f"{project.image_repository}:{release.image_tag}"

    scan_result = await scanner.scan_image(full_image_ref)

    release.scan_status = scan_result.get("status", "clean")
    release.scan_results = scan_result
    db.commit()

    report = ScanReport(
        release_id=release.id,
        image_tag=release.image_tag,
        is_simulated=scan_result.get("is_simulated", True),
        status=release.scan_status,
        critical_count=scan_result.get("critical_count", 0),
        high_count=scan_result.get("high_count", 0),
        medium_count=scan_result.get("medium_count", 0),
        low_count=scan_result.get("low_count", 0),
        vulnerabilities=scan_result.get("vulnerabilities", [])
    )

    AuditService.log_event(
        db=db,
        action="release.scan",
        entity_type="release",
        entity_id=release.id,
        user_id=current_user.id,
        username=current_user.username,
        details={"status": release.scan_status, "critical": report.critical_count}
    )

    return ApiResponse(success=True, data=report)

@router.get("/compare", response_model=ApiResponse[dict])
def compare_releases(
    project_id: str,
    from_release_id: str,
    to_release_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_owned_project(db, project_id, current_user)
    releases = db.query(Release).filter(
        Release.project_id == project_id,
        Release.id.in_([from_release_id, to_release_id]),
    ).all()
    by_id = {release.id: release for release in releases}
    if len(by_id) != 2:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or both releases not found")
    previous = by_id[from_release_id]
    current = by_id[to_release_id]
    return ApiResponse(success=True, data={
        "from": ReleaseOut.model_validate(previous),
        "to": ReleaseOut.model_validate(current),
        "changes": {
            "version": {"from": previous.version, "to": current.version},
            "image_tag": {"from": previous.image_tag, "to": current.image_tag},
            "git_commit": {"from": previous.git_commit, "to": current.git_commit},
            "changelog": current.changelog,
        },
    })
