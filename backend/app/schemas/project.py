from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

class ProjectBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    git_repo: str = Field(..., min_length=5)
    default_branch: str = "main"
    image_repository: str = Field(..., min_length=3)
    default_port: int = Field(default=3000, ge=1, le=65535)
    health_path: str = Field(default="/healthz")

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    description: Optional[str] = None
    git_repo: Optional[str] = None
    default_branch: Optional[str] = None
    image_repository: Optional[str] = None
    default_port: Optional[int] = None
    health_path: Optional[str] = None

class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    owner_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
