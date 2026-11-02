from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

class ReleaseCreate(BaseModel):
    version: str = Field(..., min_length=2, max_length=50)
    git_commit: str = Field(..., min_length=7, max_length=40)
    git_branch: str = "main"
    image_tag: str = Field(..., min_length=1)
    image_reference: Optional[str] = Field(default=None, min_length=3, max_length=255)
    image_digest: Optional[str] = Field(default=None, max_length=255)
    configuration_revision: Optional[str] = Field(default=None, max_length=255)
    commit_message: Optional[str] = None
    changelog: Optional[str] = None

class ReleaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    version: str
    git_commit: str
    git_branch: str
    image_tag: str
    image_reference: Optional[str] = None
    image_digest: Optional[str] = None
    build_status: str
    configuration_revision: Optional[str] = None
    commit_message: Optional[str] = None
    changelog: Optional[str] = None
    scan_status: str
    scan_results: Dict[str, Any]
    created_at: datetime

class VulnerabilityItem(BaseModel):
    cve_id: str
    severity: str
    package: str
    installed_version: str
    fixed_version: Optional[str] = None
    description: Optional[str] = None

class ScanReport(BaseModel):
    release_id: str
    image_tag: str
    is_simulated: bool
    status: str
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    vulnerabilities: List[VulnerabilityItem] = []
