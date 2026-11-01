from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

class EnvironmentBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    k8s_namespace: str = Field(..., min_length=2)
    k8s_cluster: str = "default"
    replicas: int = Field(default=2, ge=1, le=50)
    deployment_strategy: str = Field(default="rolling")
    canary_steps: List[int] = Field(default_factory=lambda: [10, 25, 50, 100])
    auto_rollback_enabled: bool = True
    verification_timeout_seconds: int = Field(default=60, ge=5, le=600)
    smoke_test_endpoint: str = "/healthz"
    env_vars: Dict[str, str] = Field(default_factory=dict)

class EnvironmentCreate(EnvironmentBase):
    pass

class EnvironmentUpdate(BaseModel):
    replicas: Optional[int] = None
    deployment_strategy: Optional[str] = None
    canary_steps: Optional[List[int]] = None
    auto_rollback_enabled: Optional[bool] = None
    verification_timeout_seconds: Optional[int] = None
    smoke_test_endpoint: Optional[str] = None
    env_vars: Optional[Dict[str, str]] = None

class EnvironmentOut(EnvironmentBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    current_release_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
