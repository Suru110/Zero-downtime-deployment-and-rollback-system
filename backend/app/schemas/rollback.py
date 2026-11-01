from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class RollbackTrigger(BaseModel):
    deployment_id: str
    reason: str = Field(..., min_length=5)

class RollbackEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_deployment_id: str
    environment_id: str
    failed_release_id: str
    restored_release_id: str
    is_automated: bool
    triggered_by_user_id: Optional[str] = None
    reason: str
    status: str
    details: Dict[str, Any]
    created_at: datetime
