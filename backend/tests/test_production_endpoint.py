import asyncio
from types import SimpleNamespace

import pytest

from app.adapters.k8s.production_adapter import ProductionKubernetesAdapter
from app.core.config import settings


class FakeCoreClient:
    def __init__(self, endpoints):
        self.endpoints = endpoints
        self.request = None
        self.endpoint_calls = 0

    def read_namespaced_endpoints(self, name, namespace):
        self.request = (name, namespace)
        self.endpoint_calls += 1
        if isinstance(self.endpoints, list):
            result = self.endpoints.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return self.endpoints


def make_service():
    return SimpleNamespace(
        metadata=SimpleNamespace(name="registration-login"),
        spec=SimpleNamespace(
            type="ClusterIP",
            selector={"app": "registration-login"},
            ports=[
                SimpleNamespace(port=80, target_port=3000),
                SimpleNamespace(port=9090, target_port=9090),
            ],
        ),
    )


def make_deployment():
    return SimpleNamespace(
        spec=SimpleNamespace(
            selector=SimpleNamespace(match_labels={"app": "registration-login"}),
            template=SimpleNamespace(
                metadata=SimpleNamespace(labels={"app": "registration-login"}),
                spec=SimpleNamespace(
                    containers=[
                        SimpleNamespace(
                            ports=[
                                SimpleNamespace(
                                    name="http",
                                    container_port=3000,
                                )
                            ]
                        )
                    ]
                ),
            ),
        )
    )


class FakeKubernetesClient:
    def __init__(self):
        self.deployment = make_deployment()

    def read_namespaced_deployment(self, name, namespace):
        self.request = (name, namespace)
        return self.deployment


def make_adapter(endpoints):
    adapter = ProductionKubernetesAdapter.__new__(ProductionKubernetesAdapter)
    adapter._core_client = FakeCoreClient(endpoints)
    adapter._k8s_client = FakeKubernetesClient()
    adapter.initialization_error = None
    return adapter


@pytest.mark.asyncio
async def test_quick_tunnel_waits_for_ready_service_endpoints(monkeypatch):
    adapter = make_adapter(
        SimpleNamespace(
            subsets=[
                SimpleNamespace(
                    addresses=[],
                    ports=[SimpleNamespace(port=3000)],
                )
            ]
        )
    )
    monkeypatch.setattr(settings, "CLOUDFLARE_TUNNEL_ENABLED", True)
    monkeypatch.setattr(settings, "K8S_ENDPOINT_DISCOVERY_ATTEMPTS", 1)
    monkeypatch.setattr(
        "app.adapters.k8s.production_adapter.cloudflare_tunnel_service.ensure_tunnel",
        lambda *args: pytest.fail("Tunnel creation must wait for ready endpoints."),
    )

    endpoint = await adapter.discover_service_endpoint(
        app_name="registration-login",
        namespace="registration-login-staging",
        port=3000,
        service=make_service(),
        deployment_id="deployment-ready-check",
    )

    assert endpoint["status"] == "pending"
    assert "no ready Kubernetes endpoints" in endpoint["error"]


@pytest.mark.asyncio
async def test_quick_tunnel_uses_matching_service_port_and_namespace(monkeypatch):
    core_client = FakeCoreClient(
        SimpleNamespace(
            subsets=[
                SimpleNamespace(
                    addresses=[SimpleNamespace(ip="10.0.0.8")],
                    ports=[SimpleNamespace(port=3000)],
                )
            ]
        )
    )
    adapter = ProductionKubernetesAdapter.__new__(ProductionKubernetesAdapter)
    adapter._core_client = core_client
    adapter._k8s_client = FakeKubernetesClient()
    adapter.initialization_error = None
    monkeypatch.setattr(settings, "CLOUDFLARE_TUNNEL_ENABLED", True)
    monkeypatch.setattr(settings, "K8S_ENDPOINT_DISCOVERY_ATTEMPTS", 1)
    tunnel_calls = []

    async def ensure_tunnel(*args):
        tunnel_calls.append(args)
        return {
            "status": "ready",
            "public_url": "https://real-name.trycloudflare.com",
            "tunnel_provider": "cloudflare-quick-tunnel",
        }

    monkeypatch.setattr(
        "app.adapters.k8s.production_adapter.cloudflare_tunnel_service.ensure_tunnel",
        ensure_tunnel,
    )

    endpoint = await adapter.discover_service_endpoint(
        app_name="registration-login",
        namespace="registration-login-staging",
        port=3000,
        service=make_service(),
        deployment_id="deployment-port-check",
    )

    assert core_client.request == ("registration-login", "registration-login-staging")
    assert tunnel_calls == [
        (
            "deployment-port-check",
            "registration-login-staging",
            "registration-login",
            80,
            "/healthz",
        )
    ]
    assert endpoint["status"] == "ready"
    assert endpoint["public_url"] == "https://real-name.trycloudflare.com"


@pytest.mark.asyncio
async def test_named_target_port_is_resolved_from_deployment_container(monkeypatch):
    adapter = make_adapter(
        SimpleNamespace(
            subsets=[
                SimpleNamespace(
                    addresses=[SimpleNamespace(ip="10.0.0.8")],
                    ports=[SimpleNamespace(port=3000)],
                )
            ]
        )
    )
    service = make_service()
    service.spec.ports = [SimpleNamespace(port=80, target_port="http")]
    monkeypatch.setattr(settings, "CLOUDFLARE_TUNNEL_ENABLED", True)
    monkeypatch.setattr(settings, "K8S_ENDPOINT_DISCOVERY_ATTEMPTS", 1)
    tunnel_calls = []

    async def ensure_tunnel(*args):
        tunnel_calls.append(args)
        return {
            "status": "ready",
            "public_url": "https://named-target.trycloudflare.com",
            "tunnel_provider": "cloudflare-quick-tunnel",
        }

    monkeypatch.setattr(
        "app.adapters.k8s.production_adapter.cloudflare_tunnel_service.ensure_tunnel",
        ensure_tunnel,
    )

    endpoint = await adapter.discover_service_endpoint(
        app_name="registration-login",
        namespace="registration-login-staging",
        port=3000,
        service=service,
        deployment_id="deployment-named-target",
    )

    assert tunnel_calls[0][3] == 80
    assert endpoint["target_port"] == "http"
    assert endpoint["resolved_target_port"] == 3000
    assert endpoint["service_name"] == "registration-login"


@pytest.mark.asyncio
async def test_service_selector_must_match_deployment_pod_labels(monkeypatch):
    adapter = make_adapter(
        SimpleNamespace(
            subsets=[
                SimpleNamespace(
                    addresses=[SimpleNamespace(ip="10.0.0.8")],
                    ports=[SimpleNamespace(port=3000)],
                )
            ]
        )
    )
    service = make_service()
    service.spec.selector = {"app": "some-other-app"}
    monkeypatch.setattr(settings, "CLOUDFLARE_TUNNEL_ENABLED", True)

    endpoint = await adapter.discover_service_endpoint(
        app_name="registration-login",
        namespace="registration-login-staging",
        port=3000,
        service=service,
        deployment_id="deployment-selector-mismatch",
    )

    assert endpoint["status"] == "error"
    assert "does not select the intended Deployment pods" in endpoint["error"]
    assert adapter._core_client.endpoint_calls == 0


@pytest.mark.asyncio
async def test_transient_endpoint_query_error_is_retried(monkeypatch):
    ready_endpoints = SimpleNamespace(
        subsets=[
            SimpleNamespace(
                addresses=[SimpleNamespace(ip="10.0.0.8")],
                ports=[SimpleNamespace(port=3000)],
            )
        ]
    )
    adapter = make_adapter([RuntimeError("temporary API failure"), ready_endpoints])
    monkeypatch.setattr(settings, "CLOUDFLARE_TUNNEL_ENABLED", False)
    monkeypatch.setattr(settings, "K8S_ENDPOINT_DISCOVERY_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "K8S_ENDPOINT_DISCOVERY_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(
        adapter,
        "_service_url_candidates",
        lambda *args: asyncio.sleep(0, result=[]),
    )

    endpoint = await adapter.discover_service_endpoint(
        app_name="registration-login",
        namespace="registration-login-staging",
        port=3000,
        service=make_service(),
    )

    assert endpoint["status"] == "pending"
    assert adapter._core_client.endpoint_calls == 2
