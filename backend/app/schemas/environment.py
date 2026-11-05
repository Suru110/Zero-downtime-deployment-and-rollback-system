from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.kubernetes import normalize_kubernetes_name

class EnvironmentBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    k8s_namespace: str = Field(..., min_length=2)
    k8s_cluster: str = "default"
    replicas: int = Field(default=2, ge=1, le=50)
    deployment_strategy: str = Field(default="rolling")
    canary_steps: List[int] = Field(default_factory=lambda: [10, 25, 50, 100])
    auto_rollback_enabled: bool = True
    verification_timeout_seconds: int = Field(default=60, ge=5, le=600)
    verification_attempts: int = Field(default=3, ge=1, le=10)
    smoke_test_endpoint: str = "/healthz"
    smoke_test_expected_status: int = Field(default=200, ge=100, le=599)
    smoke_test_timeout_seconds: int = Field(default=5, ge=1, le=60)
    env_vars: Dict[str, str] = Field(default_factory=dict)

    @field_validator("k8s_namespace", mode="before")
    @classmethod
    def normalize_namespace(cls, value: str) -> str:
        return normalize_kubernetes_name(value)

class EnvironmentCreate(EnvironmentBase):
    pass

class EnvironmentUpdate(BaseModel):
    k8s_namespace: Optional[str] = None
    replicas: Optional[int] = None
    deployment_strategy: Optional[str] = None
    canary_steps: Optional[List[int]] = None
    auto_rollback_enabled: Optional[bool] = None
    verification_timeout_seconds: Optional[int] = None
    verification_attempts: Optional[int] = Field(default=None, ge=1, le=10)
    smoke_test_endpoint: Optional[str] = None
    smoke_test_expected_status: Optional[int] = Field(default=None, ge=100, le=599)
    smoke_test_timeout_seconds: Optional[int] = Field(default=None, ge=1, le=60)
    env_vars: Optional[Dict[str, str]] = None

    @field_validator("k8s_namespace", mode="before")
    @classmethod
    def normalize_namespace(cls, value: Optional[str]) -> Optional[str]:
        return normalize_kubernetes_name(value) if value is not None else None

class EnvironmentOut(EnvironmentBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    current_release_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
