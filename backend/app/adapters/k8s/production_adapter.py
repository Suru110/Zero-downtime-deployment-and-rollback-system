import os
import re
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.adapters.base import BaseDeploymentAdapter, AdapterResult
from app.core.config import settings

class ProductionKubernetesAdapter(BaseDeploymentAdapter):
    def __init__(self):
        self._k8s_client = None
        self._init_client()

    @property
    def adapter_name(self) -> str:
        return "k8s-production-adapter"

    @property
    def is_simulated(self) -> bool:
        return False

    def _init_client(self):
        try:
            from kubernetes import client, config
            if settings.KUBERNETES_IN_CLUSTER:
                config.load_incluster_config()
            elif settings.KUBECONFIG_PATH and os.path.exists(os.path.expanduser(settings.KUBECONFIG_PATH)):
                config.load_kube_config(config_file=os.path.expanduser(settings.KUBECONFIG_PATH))
            else:
                try:
                    config.load_kube_config()
                except Exception:
                    # No local kubeconfig found
                    self._k8s_client = None
                    return
            self._k8s_client = client.AppsV1Api()
            self._core_client = client.CoreV1Api()
        except Exception:
            self._k8s_client = None

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
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._/-]*:[A-Za-z0-9][A-Za-z0-9._-]*$", image):
            return AdapterResult(
                success=False,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message="Invalid image reference.",
                details={"error": "Image must use a repository:name reference."},
                logs=logs,
            )
        if not self._k8s_client:
            self._log(logs, "ERROR", "Kubernetes cluster connection not available. Please verify Kubeconfig.")
            return AdapterResult(
                success=False,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message="Cannot connect to target Kubernetes cluster.",
                details={"error": "Kubeconfig not configured or cluster unreachable."},
                logs=logs
            )
        
        try:
            from kubernetes import client
            # Patch deployment image
            self._log(logs, "INFO", f"Triggering deployment patch for '{app_name}' in namespace '{namespace}'")
            patch_body = {
                "spec": {
                    "replicas": replicas,
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": app_name,
                                    "image": image,
                                    "ports": [{"containerPort": port}],
                                    "env": [{"name": k, "value": v} for k, v in env_vars.items()]
                                }
                            ]
                        }
                    }
                }
            }
            self._k8s_client.patch_namespaced_deployment(
                name=app_name,
                namespace=namespace,
                body=patch_body
            )
            self._log(logs, "INFO", f"Updated image to '{image}' with {replicas} replicas.")
            ready = 0
            for _ in range(settings.DEFAULT_HEALTH_CHECK_MAX_ATTEMPTS):
                deployment = self._k8s_client.read_namespaced_deployment(
                    name=app_name, namespace=namespace
                )
                ready = deployment.status.ready_replicas or 0
                if ready >= replicas and (deployment.status.updated_replicas or 0) >= replicas:
                    break
                await asyncio.sleep(settings.DEFAULT_HEALTH_CHECK_INTERVAL_SECONDS)
            if ready < replicas:
                self._log(logs, "ERROR", f"Rollout is not ready: {ready}/{replicas} replicas ready.")
                return AdapterResult(
                    success=False,
                    is_simulated=False,
                    adapter_name=self.adapter_name,
                    message="Kubernetes rollout did not become ready.",
                    details={"ready_replicas": ready, "desired_replicas": replicas},
                    logs=logs,
                )
            return AdapterResult(
                success=True,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message="Kubernetes Deployment resource successfully patched.",
                details={"app": app_name, "image": image},
                logs=logs
            )
        except Exception as e:
            self._log(logs, "ERROR", f"Kubernetes API error ({type(e).__name__}).")
            return AdapterResult(
                success=False,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message="Failed to update deployment through the Kubernetes API.",
                details={"error_type": type(e).__name__},
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
        if not self._k8s_client:
            self._log(logs, "ERROR", "Kubernetes cluster connection not available.")
            return AdapterResult(
                success=False,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message="Cluster unreachable for rollback.",
                logs=logs
            )
        try:
            patch_body = {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{"name": app_name, "image": target_image}]
                        }
                    }
                }
            }
            self._k8s_client.patch_namespaced_deployment(name=app_name, namespace=namespace, body=patch_body)
            self._log(logs, "WARN", f"Emergency rollback: Patched deployment '{app_name}' to image '{target_image}'.")
            ready = 0
            for _ in range(settings.DEFAULT_HEALTH_CHECK_MAX_ATTEMPTS):
                deployment = self._k8s_client.read_namespaced_deployment(
                    name=app_name, namespace=namespace
                )
                ready = deployment.status.ready_replicas or 0
                if ready >= replicas:
                    break
                await asyncio.sleep(settings.DEFAULT_HEALTH_CHECK_INTERVAL_SECONDS)
            if ready < replicas:
                self._log(logs, "ERROR", f"Rollback readiness failed: {ready}/{replicas} replicas ready.")
                return AdapterResult(
                    success=False,
                    is_simulated=False,
                    adapter_name=self.adapter_name,
                    message="Rollback patch applied but readiness verification failed.",
                    details={"ready_replicas": ready, "desired_replicas": replicas},
                    logs=logs,
                )
            return AdapterResult(
                success=True,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message=f"Successfully restored deployment to {target_image}",
                details={"restored_image": target_image},
                logs=logs
            )
        except Exception as e:
            self._log(logs, "ERROR", f"Rollback execution failed ({type(e).__name__}).")
            return AdapterResult(
                success=False,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message="Rollback failed through the Kubernetes API.",
                details={"error_type": type(e).__name__},
                logs=logs
            )

    async def get_pod_status(self, app_name: str, namespace: str) -> Dict[str, Any]:
        if not self._k8s_client:
            return {"status": "Disconnected", "ready_replicas": 0, "desired_replicas": 0, "is_simulated": False}
        try:
            dep = self._k8s_client.read_namespaced_deployment(name=app_name, namespace=namespace)
            ready = dep.status.ready_replicas or 0
            desired = dep.spec.replicas or 0
            return {
                "app_name": app_name,
                "namespace": namespace,
                "is_simulated": False,
                "ready_replicas": ready,
                "desired_replicas": desired,
                "status": "Healthy" if ready == desired else "Degraded"
            }
        except Exception as e:
            return {"error": "Kubernetes status query failed.", "error_type": type(e).__name__, "is_simulated": False, "status": "Error"}
