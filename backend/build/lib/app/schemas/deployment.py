from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict

class DeploymentTrigger(BaseModel):
    project_id: str
    environment_id: str
    release_id: str
    override_strategy: Optional[str] = None
    dry_run: bool = False
    simulate_failure: bool = False

class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str

class DeploymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    environment_id: str
    release_id: str
    triggered_by: Optional[str] = None
    status: str
    strategy: str
    progress: int
    is_simulated: bool
    adapter_name: str
    logs: List[Dict[str, Any]]
    metadata_info: Dict[str, Any]
    started_at: datetime
    finished_at: Optional[datetime] = None
