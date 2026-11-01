import httpx
from datetime import datetime
from typing import Dict, Any, List
from app.adapters.base import BaseGitOpsAdapter, AdapterResult
from app.core.config import settings

class ProductionArgoCDAdapter(BaseGitOpsAdapter):
    @property
    def adapter_name(self) -> str:
        return "argocd-production-adapter"

    @property
    def is_simulated(self) -> bool:
        return False

    async def sync_application(self, app_name: str, revision: str) -> AdapterResult:
        logs: List[Dict[str, Any]] = []
        url = f"{settings.ARGO_CD_SERVER.rstrip('/')}/api/v1/applications/{app_name}/sync"
        headers = {"Authorization": f"Bearer {settings.ARGO_CD_AUTH_TOKEN}"}
        
        try:
            async with httpx.AsyncClient(verify=not settings.ARGO_CD_INSECURE_SKIP_TLS_VERIFY, timeout=10.0) as client:
                res = await client.post(url, json={"revision": revision, "prune": True}, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    logs.append({"timestamp": datetime.utcnow().isoformat() + "Z", "level": "INFO", "message": f"Argo CD sync triggered: status={data.get('status')}"})
                    return AdapterResult(
                        success=True,
                        is_simulated=False,
                        adapter_name=self.adapter_name,
                        message="Argo CD sync request accepted.",
                        details=data,
                        logs=logs
                    )
                else:
                    logs.append({"timestamp": datetime.utcnow().isoformat() + "Z", "level": "ERROR", "message": f"Argo CD API returned HTTP {res.status_code}: {res.text}"})
                    return AdapterResult(
                        success=False,
                        is_simulated=False,
                        adapter_name=self.adapter_name,
                        message=f"Argo CD returned HTTP {res.status_code}",
                        logs=logs
                    )
        except Exception as e:
            logs.append({"timestamp": datetime.utcnow().isoformat() + "Z", "level": "ERROR", "message": f"Argo CD connection failed: {str(e)}"})
            return AdapterResult(
                success=False,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message=f"Argo CD unreachable: {str(e)}",
                logs=logs
            )
