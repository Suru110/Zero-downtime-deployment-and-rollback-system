import os
import re
import asyncio
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlsplit
from app.adapters.base import BaseDeploymentAdapter, AdapterResult
from app.core.config import settings
from app.core.kubernetes import normalize_kubernetes_name

class ProductionKubernetesAdapter(BaseDeploymentAdapter):
    _minikube_tunnels: Dict[str, subprocess.Popen] = {}
    _minikube_tunnel_urls: Dict[str, str] = {}

    def __init__(self):
        self._k8s_client = None
        self._networking_client = None
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
            self._networking_client = client.NetworkingV1Api()
        except Exception:
            self._k8s_client = None

    def _log(self, logs: List[Dict[str, Any]], level: str, message: str) -> None:
        logs.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message
        })

    @staticmethod
    def _api_error_message(exc: Exception) -> str:
        body = getattr(exc, "body", None)
        reason = getattr(exc, "reason", None)
        status = getattr(exc, "status", None)
        if body:
            return f"status={status}, reason={reason}, body={body}"
        return f"status={status}, reason={reason or str(exc)}"

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
        simulate_failure: bool = False,
        health_path: str = "/healthz",
    ) -> AdapterResult:
        logs: List[Dict[str, Any]] = []
        original_app_name = app_name
        app_name = normalize_kubernetes_name(app_name)
        if app_name != original_app_name:
            self._log(
                logs,
                "WARN",
                f"Normalized invalid Kubernetes app name '{original_app_name}' to '{app_name}'.",
            )
        original_namespace = namespace
        namespace = normalize_kubernetes_name(namespace)
        if namespace != original_namespace:
            self._log(
                logs,
                "WARN",
                f"Normalized invalid Kubernetes namespace '{original_namespace}' to '{namespace}'.",
            )
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
                    type="NodePort",
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
                existing_service = self._core_client.read_namespaced_service(
                    name=app_name, namespace=namespace
                )
                existing_ports = existing_service.spec.ports or []
                if existing_service.spec.cluster_ip:
                    svc_manifest.spec.cluster_ip = existing_service.spec.cluster_ip
                # The attribute name for clusterIPs varies across kubernetes-client
                # versions: 'cluster_ips' in older releases, 'cluster_i_ps' in v31+.
                for _attr in ("cluster_i_ps", "cluster_ips"):
                    _val = getattr(existing_service.spec, _attr, None)
                    if _val:
                        try:
                            setattr(svc_manifest.spec, _attr, _val)
                        except AttributeError:
                            pass
                        break
                if existing_ports and existing_ports[0].node_port:
                    svc_manifest.spec.ports[0].node_port = existing_ports[0].node_port
                self._core_client.patch_namespaced_service(name=app_name, namespace=namespace, body=svc_manifest)
                self._log(logs, "INFO", f"Patched existing Service '{app_name}'.")
            except Exception as exc:
                if not isinstance(exc, client.ApiException) or exc.status != 404:
                    raise
                self._core_client.create_namespaced_service(namespace=namespace, body=svc_manifest)
                self._log(logs, "INFO", f"Created Service '{app_name}' on port {port}.")
            service = self._core_client.read_namespaced_service(name=app_name, namespace=namespace)
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
            endpoint = await self.discover_service_endpoint(
                app_name=app_name,
                namespace=namespace,
                port=port,
                health_path=health_path,
                service=service,
            )
            public_url = endpoint.get("public_url")
            if public_url:
                self._log(logs, "INFO", f"Application URL available at {public_url}")
            else:
                self._log(
                    logs,
                    "WARN",
                    endpoint.get("error", "Service created, but no reachable public URL could be discovered."),
                )
            return AdapterResult(
                success=True,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message="Kubernetes Deployment resource successfully patched.",
                details={
                    "app": app_name,
                    "image": image,
                    "public_url": public_url,
                    "endpoint_status": endpoint["status"],
                    **({"endpoint_error": endpoint["error"]} if endpoint.get("error") else {}),
                    "service_type": service.spec.type,
                    "service_port": port,
                    "target_port": port,
                },
                logs=logs
            )
        except Exception as e:
            detail = self._api_error_message(e)
            self._log(logs, "ERROR", f"Kubernetes API error ({type(e).__name__}): {detail}")
            return AdapterResult(
                success=False,
                is_simulated=False,
                adapter_name=self.adapter_name,
                message="Failed to update deployment through the Kubernetes API.",
                details={"error_type": type(e).__name__, "error": detail},
                logs=logs
            )

    async def discover_service_endpoint(
        self,
        app_name: str,
        namespace: str,
        port: int,
        health_path: str = "/healthz",
        service: Any = None,
    ) -> Dict[str, Any]:
        if not self._core_client:
            return {
                "status": "error",
                "error": "Kubernetes client is not connected.",
            }
        try:
            if service is None:
                try:
                    service = self._core_client.read_namespaced_service(
                        name=app_name,
                        namespace=namespace,
                    )
                except Exception as exc:
                    from kubernetes import client as k8s_client
                    if isinstance(exc, k8s_client.ApiException) and exc.status == 404:
                        return {
                            "status": "pending",
                            "error": (
                                f"Service '{app_name}' not found in namespace '{namespace}'. "
                                "The deployment may still be starting up."
                            ),
                        }
                    raise
            service_type = service.spec.type or "ClusterIP"
            candidates = await self._service_url_candidates(service, namespace, port)
            if not candidates:
                if service_type == "ClusterIP":
                    error = (
                        f"Service '{app_name}' is ClusterIP and has no externally reachable endpoint. "
                        "Expose it with NodePort, LoadBalancer, or Ingress."
                    )
                else:
                    error = f"Service '{app_name}' has no assigned external endpoint yet."
                return {"status": "pending", "error": error, "service_type": service_type}

            last_error = "Endpoint did not respond."
            for attempt in range(settings.K8S_ENDPOINT_DISCOVERY_ATTEMPTS):
                for candidate in candidates:
                    if await self._endpoint_is_reachable(candidate, health_path):
                        return {
                            "status": "ready",
                            "public_url": candidate,
                            "service_type": service_type,
                        }
                    last_error = f"Endpoint {candidate} is not reachable yet."
                if attempt + 1 < settings.K8S_ENDPOINT_DISCOVERY_ATTEMPTS:
                    await asyncio.sleep(settings.K8S_ENDPOINT_DISCOVERY_INTERVAL_SECONDS)
            return {"status": "pending", "error": last_error, "service_type": service_type}
        except Exception as exc:
            return {
                "status": "error",
                "error": f"Endpoint discovery failed: {type(exc).__name__}: {exc}",
            }

    async def _service_url_candidates(
        self,
        service: Any,
        namespace: str,
        port: int,
    ) -> List[str]:
        candidates: List[str] = []
        service_type = service.spec.type or "ClusterIP"
        node_port = next(
            (item.node_port for item in (service.spec.ports or []) if item.node_port),
            None,
        )
        if settings.K8S_PUBLIC_BASE_URL and service_type != "ClusterIP":
            configured_url = settings.K8S_PUBLIC_BASE_URL.rstrip("/")
            if urlsplit(configured_url).port:
                candidates.append(configured_url)
            elif node_port:
                candidates.append(
                    f"{configured_url}:{node_port if service_type == 'NodePort' else port}"
                )
            elif service_type == "LoadBalancer":
                candidates.append(f"{configured_url}:{port}")
        load_balancer = getattr(service.status, "load_balancer", None)
        ingress = getattr(load_balancer, "ingress", None) if load_balancer else None
        if ingress:
            address = getattr(ingress[0], "hostname", None) or getattr(ingress[0], "ip", None)
            if address:
                candidates.append(
                    f"http://{address}:{node_port if service_type == 'NodePort' else port}"
                )
        if self._networking_client:
            try:
                ingresses = self._networking_client.list_namespaced_ingress(namespace).items
                for ingress_resource in ingresses:
                    for rule in ingress_resource.spec.rules or []:
                        if rule.host:
                            scheme = "https" if any(
                                tls.hosts and rule.host in tls.hosts
                                for tls in (ingress_resource.spec.tls or [])
                            ) else "http"
                            candidates.append(f"{scheme}://{rule.host}")
            except Exception:
                pass
        if service_type == "NodePort" and node_port:
            # 1. Try `minikube ip` first — fast and reliable on Docker driver
            try:
                minikube_command = ["minikube", "ip"]
                if settings.K8S_MINIKUBE_PROFILE:
                    minikube_command.extend(["-p", settings.K8S_MINIKUBE_PROFILE])
                minikube_ip = self._command_output(minikube_command)
                if minikube_ip:
                    candidates.append(f"http://{minikube_ip}:{node_port}")
            except (FileNotFoundError, OSError):
                pass

            # 2. Try `minikube service --url` tunnel (works on Docker driver when
            #    the minikube IP is not directly reachable from the host)
            minikube_url = self._minikube_service_url(service, namespace)
            if minikube_url:
                candidates.append(minikube_url)

            # 3. Node ExternalIP fallback (bare-metal / cloud clusters)
            try:
                for node in self._core_client.list_node().items:
                    for address in node.status.addresses or []:
                        if address.type == "ExternalIP":
                            candidates.append(f"http://{address.address}:{node_port}")
            except Exception:
                pass

            # 4. Last-resort: localhost + NodePort (works if minikube tunnel is
            #    running or the cluster is port-forwarded to the host)
            candidates.append(f"http://127.0.0.1:{node_port}")

        return list(dict.fromkeys(candidates))

    async def _endpoint_is_reachable(self, base_url: str, health_path: str) -> bool:
        path = health_path if health_path.startswith("/") else f"/{health_path}"
        url = f"{base_url.rstrip('/')}{path}"
        return await asyncio.to_thread(self._probe_url, url)

    @staticmethod
    def _probe_url(url: str) -> bool:
        try:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=settings.K8S_ENDPOINT_VERIFY_TIMEOUT_SECONDS) as response:
                return response.status < 500
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _minikube_service_url(self, service: Any, namespace: str) -> Optional[str]:
        tunnel_key = f"{namespace}/{service.metadata.name}"
        existing_tunnel = self._minikube_tunnels.get(tunnel_key)
        if existing_tunnel and existing_tunnel.poll() is None:
            return self._minikube_tunnel_urls.get(tunnel_key)
        command = ["minikube", "service", service.metadata.name, "-n", namespace, "--url"]
        if settings.K8S_MINIKUBE_PROFILE:
            command.extend(["-p", settings.K8S_MINIKUBE_PROFILE])
        try:
            tunnel = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            self._minikube_tunnels[tunnel_key] = tunnel
            url = self._tunnel_url(tunnel)
            if url:
                self._minikube_tunnel_urls[tunnel_key] = url
                return url
            self._minikube_tunnels.pop(tunnel_key, None)
            tunnel.terminate()
        except (FileNotFoundError, OSError):
            return None
        return None

    @staticmethod
    def _command_output(command: List[str]) -> Optional[str]:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return completed.stdout.strip() if completed.returncode == 0 else None

    @staticmethod
    def _tunnel_url(tunnel: subprocess.Popen) -> Optional[str]:
        """Read stdout lines until we find an http(s) URL or the process ends.

        On Windows with the Docker driver, minikube service --url emits
        several informational lines before printing the actual URL, so we
        must scan all output rather than only the first line.
        Uses a short per-line timeout via select so we don't block forever.
        """
        if not tunnel.stdout:
            return None
        import threading

        found_url: list = []

        def _reader() -> None:
            try:
                for _ in range(30):  # scan up to 30 lines
                    line = tunnel.stdout.readline()  # type: ignore[union-attr]
                    if not line:
                        break
                    match = re.search(r"https?://\S+", line.strip())
                    if match:
                        found_url.append(match.group(0))
                        return
            except (OSError, ValueError):
                pass

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()
        reader.join(timeout=15)  # give minikube up to 15 s to print the URL
        return found_url[0] if found_url else None

    async def rollback(
        self,
        app_name: str,
        namespace: str,
        target_image: str,
        replicas: int
    ) -> AdapterResult:
        logs: List[Dict[str, Any]] = []
        app_name = normalize_kubernetes_name(app_name)
        namespace = normalize_kubernetes_name(namespace)
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
        app_name = normalize_kubernetes_name(app_name)
        namespace = normalize_kubernetes_name(namespace)
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
        service_name = normalize_kubernetes_name(service_name)
        namespace = normalize_kubernetes_name(namespace)
        proxy_path = path.lstrip("/")
        await asyncio.to_thread(
            self._core_client.connect_get_namespaced_service_proxy_with_path,
            service_name,
            namespace,
            proxy_path,
        )
        return 200
