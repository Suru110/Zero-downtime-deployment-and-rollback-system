import asyncio
from datetime import datetime
from typing import Dict, Any, List
from app.adapters.base import BaseGitOpsAdapter, AdapterResult

class MockArgoCDAdapter(BaseGitOpsAdapter):
    @property
    def adapter_name(self) -> str:
        return "mock-argocd-adapter"

    @property
    def is_simulated(self) -> bool:
        return True

    async def sync_application(self, app_name: str, revision: str) -> AdapterResult:
        logs: List[Dict[str, Any]] = [
            {"timestamp": datetime.utcnow().isoformat() + "Z", "level": "INFO", "message": f"[SIMULATION] Connecting to Argo CD mock controller"},
            {"timestamp": datetime.utcnow().isoformat() + "Z", "level": "INFO", "message": f"[SIMULATION] Triggering GitOps sync for '{app_name}' to target revision '{revision}'"}
        ]
        await asyncio.sleep(0.4)
        logs.append({"timestamp": datetime.utcnow().isoformat() + "Z", "level": "INFO", "message": f"[SIMULATION] Argo CD Application '{app_name}' is Synced and Healthy."})
        return AdapterResult(
            success=True,
            is_simulated=True,
            adapter_name=self.adapter_name,
            message="GitOps sync completed in simulation mode.",
            details={"sync_status": "Synced", "health_status": "Healthy", "revision": revision},
            logs=logs
        )
