import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.adapters.base import BaseDeploymentAdapter, AdapterResult

class MockKubernetesAdapter(BaseDeploymentAdapter):
    @property
    def adapter_name(self) -> str:
        return "mock-k8s-adapter"

    @property
    def is_simulated(self) -> bool:
        return True

    def _log(self, logs: List[Dict[str, Any]], level: str, message: str) -> None:
        logs.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message
        })

    async def deploy(
        self,
        app_name: str,
        namespace: str,
        image: str,
        replicas: int,
        port: int,
        env_vars: Dict[str, str],
        strategy: str,
        canary_steps: Optional[List[int]] = None,
        simulate_failure: bool = False
    ) -> AdapterResult:
        logs: List[Dict[str, Any]] = []
        self._log(logs, "INFO", f"[SIMULATION] Connecting to simulated cluster namespace: '{namespace}'")
        self._log(logs, "INFO", f"[SIMULATION] Applying Deployment manifest for '{app_name}' with image '{image}', replicas={replicas}, strategy={strategy}")
        
        await asyncio.sleep(0.3)

        if strategy == "canary":
            steps = canary_steps or [10, 25, 50, 100]
            self._log(logs, "INFO", f"[SIMULATION] Initiating Canary rollout with traffic steps: {steps}")
            for step in steps:
                self._log(logs, "INFO", f"[SIMULATION] Shifting {step}% traffic to canary pods...")
                await asyncio.sleep(0.2)
                if simulate_failure and step >= 25:
                    self._log(logs, "ERROR", f"[SIMULATION] Error rate breached SLA threshold at {step}% traffic! Pod health check failed.")
                    return AdapterResult(
                        success=False,
                        is_simulated=True,
                        adapter_name=self.adapter_name,
                        message=f"Canary health verification failed at {step}% traffic step.",
                        details={"traffic_split": step, "failed_step": True},
                        logs=logs
                    )
                self._log(logs, "INFO", f"[SIMULATION] Step {step}% validated healthy. Moving forward.")
        else:
            # Rolling update with maxSurge=25% and maxUnavailable=0
            surge_replicas = max(1, int(replicas * 0.25))
            self._log(logs, "INFO", f"[SIMULATION] Rolling update policy: maxSurge={surge_replicas}, maxUnavailable=0")
            self._log(logs, "INFO", f"[SIMULATION] Spawning {surge_replicas} surge pod(s) with new image...")
            await asyncio.sleep(0.3)
            
            if simulate_failure:
                self._log(logs, "ERROR", f"[SIMULATION] Pod '{app_name}-surge-7f89d' failed readiness probe: HTTP 500 Internal Server Error at {port}/healthz")
                self._log(logs, "ERROR", f"[SIMULATION] CrashLoopBackOff: Container failed to establish database connectivity.")
                return AdapterResult(
                    success=False,
                    is_simulated=True,
                    adapter_name=self.adapter_name,
                    message="Simulated deployment failed readiness probe verification.",
                    details={"error": "Readiness probe failed", "failed_replica": f"{app_name}-surge-7f89d"},
                    logs=logs
                )

            self._log(logs, "INFO", f"[SIMULATION] Readiness probe passed on {replicas} updated pod(s). Terminating old replica set.")
            await asyncio.sleep(0.2)

        self._log(logs, "INFO", f"[SIMULATION] Deployment completed successfully with zero downtime.")
        return AdapterResult(
            success=True,
            is_simulated=True,
            adapter_name=self.adapter_name,
            message="Simulated zero-downtime deployment finished cleanly.",
            details={"strategy": strategy, "active_replicas": replicas, "image": image},
            logs=logs
        )

    async def rollback(
        self,
        app_name: str,
        namespace: str,
        target_image: str,
        replicas: int
    ) -> AdapterResult:
        logs: List[Dict[str, Any]] = []
        self._log(logs, "WARN", f"[SIMULATION] Initiating atomic emergency rollback for '{app_name}' in '{namespace}'")
        self._log(logs, "INFO", f"[SIMULATION] Reverting image to previous known-good release: '{target_image}'")
        await asyncio.sleep(0.3)
        self._log(logs, "INFO", f"[SIMULATION] Re-routing ingress traffic away from failed revision.")
        self._log(logs, "INFO", f"[SIMULATION] Restoring {replicas} pods from previous deployment replica set.")
        await asyncio.sleep(0.2)
        self._log(logs, "INFO", f"[SIMULATION] Rollback verified: All {replicas} pods responding 200 OK.")

        return AdapterResult(
            success=True,
            is_simulated=True,
            adapter_name=self.adapter_name,
            message=f"Rollback to {target_image} successfully executed.",
            details={"restored_image": target_image, "active_replicas": replicas},
            logs=logs
        )

    async def get_pod_status(self, app_name: str, namespace: str) -> Dict[str, Any]:
        return {
            "app_name": app_name,
            "namespace": namespace,
            "is_simulated": True,
            "ready_replicas": 3,
            "desired_replicas": 3,
            "status": "Running",
            "restarts": 0
        }
