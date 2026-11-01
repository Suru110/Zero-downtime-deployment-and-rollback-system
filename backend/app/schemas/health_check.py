from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict

class HealthCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    deployment_id: str
    check_type: str
    status: str
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    details: Dict[str, Any]
    executed_at: datetime

class HealthCheckCreate(BaseModel):
    check_type: str
    status: str
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    details: Dict[str, Any] = {}
