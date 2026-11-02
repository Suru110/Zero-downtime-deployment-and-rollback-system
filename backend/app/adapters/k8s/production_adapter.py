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

            # Ensure namespace exists
            try:
                self._core_client.read_namespace(name=namespace)
                self._log(logs, "INFO", f"Namespace '{namespace}' exists.")
            except Exception as exc:
                from kubernetes import client
                if not isinstance(exc, client.ApiException) or exc.status != 404:
                    raise
                ns_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace))
                self._core_client.create_namespace(body=ns_body)
                self._log(logs, "INFO", f"Created namespace '{namespace}'.")

            # Build full Deployment manifest with rolling update strategy and probes
            deployment_env = dict(env_vars)
            health_path = deployment_env.pop("HEALTH_PATH", "/healthz")
            deployment_manifest = client.V1Deployment(
                metadata=client.V1ObjectMeta(
                    name=app_name,
                    namespace=namespace,
                    labels={"app": app_name, "managed-by": "releasepilot"},
                ),
                spec=client.V1DeploymentSpec(
                    replicas=replicas,
                    selector=client.V1LabelSelector(match_labels={"app": app_name}),
                    strategy=client.V1DeploymentStrategy(
                        type="RollingUpdate",
                        rolling_update=client.V1RollingUpdateDeployment(
                            max_surge=1,
                            max_unavailable=0,
                        ),
                    ),
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(labels={"app": app_name}),
                        spec=client.V1PodSpec(
                            termination_grace_period_seconds=30,
                            containers=[
                                client.V1Container(
                                    name=app_name,
                                    image=image,
                                    ports=[client.V1ContainerPort(container_port=port)],
                                    env=[
                                        client.V1EnvVar(name=k, value=v)
                                        for k, v in deployment_env.items()
                                    ],
                                    startup_probe=client.V1Probe(
                                        http_get=client.V1HTTPGetAction(
                                            path=health_path,
                                            port=port,
                                        ),
                                        failure_threshold=30,
                                        period_seconds=5,
                                    ),
                                    readiness_probe=client.V1Probe(
                                        http_get=client.V1HTTPGetAction(
                                            path=health_path,
                                            port=port,
                                        ),
                                        initial_delay_seconds=5,
                                        period_seconds=10,
                                        timeout_seconds=5,
                                        failure_threshold=3,
                                    ),
                                    liveness_probe=client.V1Probe(
                                        http_get=client.V1HTTPGetAction(
                                            path=health_path,
                                            port=port,
                                        ),
                                        initial_delay_seconds=15,
                                        period_seconds=20,
                                        timeout_seconds=5,
                                        failure_threshold=3,
                                    ),
                                )
                            ],
                        ),
                    ),
                ),
            )

            # Also ensure a Service exists for this deployment
            svc_manifest = client.V1Service(
                metadata=client.V1ObjectMeta(
                    name=app_name,
                    namespace=namespace,
                    labels={"app": app_name, "managed-by": "releasepilot"},
                ),
                spec=client.V1ServiceSpec(
                    selector={"app": app_name},
                    ports=[client.V1ServicePort(port=port, target_port=port)],
                    type="ClusterIP",
                ),
            )

            # Create-or-patch Deployment
            try:
                self._k8s_client.read_namespaced_deployment(name=app_name, namespace=namespace)
                self._k8s_client.patch_namespaced_deployment(
                    name=app_name, namespace=namespace, body=deployment_manifest
                )
                self._log(logs, "INFO", f"Patched existing Deployment '{app_name}' to image '{image}' with {replicas} replicas.")
            except Exception as exc:
                if not isinstance(exc, client.ApiException) or exc.status != 404:
                    raise
                self._k8s_client.create_namespaced_deployment(namespace=namespace, body=deployment_manifest)
                self._log(logs, "INFO", f"Created new Deployment '{app_name}' with image '{image}', {replicas} replicas.")

            # Create-or-patch Service
            try:
                self._core_client.read_namespaced_service(name=app_name, namespace=namespace)
                self._core_client.patch_namespaced_service(name=app_name, namespace=namespace, body=svc_manifest)
                self._log(logs, "INFO", f"Patched existing Service '{app_name}'.")
            except Exception as exc:
                if not isinstance(exc, client.ApiException) or exc.status != 404:
                    raise
                self._core_client.create_namespaced_service(namespace=namespace, body=svc_manifest)
                self._log(logs, "INFO", f"Created Service '{app_name}' on port {port}.")
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

    async def check_service_health(self, service_name: str, namespace: str, path: str) -> int:
        """Check a ClusterIP service through the Kubernetes API proxy.

        This works when ReleasePilot runs outside the cluster, where the
        service DNS name is not resolvable from the local machine.
        """
        if not self._core_client:
            raise RuntimeError("Kubernetes cluster connection not available.")
        proxy_path = path.lstrip("/")
        await asyncio.to_thread(
            self._core_client.connect_get_namespaced_service_proxy_with_path,
            service_name,
            namespace,
            proxy_path,
        )
        return 200
