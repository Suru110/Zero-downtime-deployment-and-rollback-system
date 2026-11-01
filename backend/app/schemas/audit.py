from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    action: str
    entity_type: str
    entity_id: str
    ip_address: Optional[str] = None
    details: Dict[str, Any]
    created_at: datetime
