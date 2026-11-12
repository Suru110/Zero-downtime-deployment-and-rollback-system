import pytest

from app.core.config import settings
from app.services.cloudflare_tunnel import (
    CloudflareTunnelService,
    TunnelHandle,
)


class FakeProcess:
    def __init__(self, returncode=None):
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


def make_handle(key: str, public_url=None, cloudflared_code=None):
    handle = TunnelHandle(
        key=key,
        namespace=f"{key}-namespace",
        service_name=f"{key}-service",
        service_port=80,
        local_port=40000,
        local_url="http://127.0.0.1:40000",
        public_url=public_url,
        port_forward=FakeProcess(),
        cloudflared=FakeProcess(cloudflared_code),
    )
    if public_url:
        handle.output.append(public_url)
    return handle


def test_quick_tunnel_url_is_parsed_from_cloudflared_output():
    service = CloudflareTunnelService()
    handle = make_handle("deployment-1")
    handle.output.append(
        "INF | Your quick Tunnel has been created! "
        "https://sample-tunnel.trycloudflare.com"
    )

    assert service._wait_for_url(handle)
    assert handle.public_url == "https://sample-tunnel.trycloudflare.com"


def test_public_endpoint_is_verified_before_ready(monkeypatch):
    service = CloudflareTunnelService()
    handle = make_handle("deployment-1", "https://sample.trycloudflare.com")
    monkeypatch.setattr(service, "_verify_url", lambda url, path: url.startswith("https://"))
    monkeypatch.setattr(settings, "TUNNEL_STARTUP_TIMEOUT", 0.1)

    service._tunnels[handle.key] = handle
    result = service._ensure_tunnel(
        handle.key,
        handle.namespace,
        handle.service_name,
        handle.service_port,
        "/healthz",
    )

    assert result["status"] == "ready"
    assert result["tunnel_provider"] == "cloudflare-quick-tunnel"
    assert result["last_verified_at"]


def test_tunnel_startup_timeout_cleans_up(monkeypatch):
    service = CloudflareTunnelService()
    handle = make_handle("deployment-timeout")
    monkeypatch.setattr(service, "_start_handle", lambda *args: handle)
    monkeypatch.setattr(service, "_verify_url", lambda url, path: False)
    monkeypatch.setattr(settings, "TUNNEL_STARTUP_TIMEOUT", 0.01)
    monkeypatch.setattr(settings, "TUNNEL_PUBLIC_ENDPOINT_TIMEOUT", 0.01)

    with pytest.raises(RuntimeError, match="Quick Tunnel URL"):
        service._ensure_tunnel(
            handle.key,
            handle.namespace,
            handle.service_name,
            handle.service_port,
            "/healthz",
        )

    assert handle.port_forward.terminated
    assert handle.cloudflared.poll() is not None
    assert handle.key not in service._tunnels


def test_port_forward_failure_is_reported(monkeypatch):
    service = CloudflareTunnelService()

    def fail_start(*args):
        raise RuntimeError("Kubernetes port-forward did not become reachable.")

    monkeypatch.setattr(service, "_start_handle", fail_start)

    with pytest.raises(RuntimeError, match="port-forward"):
        service._ensure_tunnel("deployment-failed", "ns", "service", 80, "/healthz")


def test_cloudflared_failure_is_reported_and_cleaned(monkeypatch):
    service = CloudflareTunnelService()
    handle = make_handle("deployment-cloudflared-failed", cloudflared_code=1)
    monkeypatch.setattr(service, "_start_handle", lambda *args: handle)

    with pytest.raises(RuntimeError, match="Quick Tunnel URL"):
        service._ensure_tunnel(
            handle.key,
            handle.namespace,
            handle.service_name,
            handle.service_port,
            "/healthz",
        )

    assert handle.port_forward.terminated
    assert handle.cloudflared.poll() is not None


def test_multiple_deployments_have_isolated_tunnels(monkeypatch):
    service = CloudflareTunnelService()
    handles = {}

    def start_handle(key, namespace, service_name, service_port):
        handle = make_handle(key, f"https://{key}.trycloudflare.com")
        handles[key] = handle
        return handle

    monkeypatch.setattr(service, "_start_handle", start_handle)
    monkeypatch.setattr(service, "_verify_url", lambda url, path: True)

    first = service._ensure_tunnel("deployment-1", "ns-a", "service-a", 80, "/healthz")
    second = service._ensure_tunnel("deployment-2", "ns-b", "service-b", 81, "/healthz")

    assert first["public_url"] != second["public_url"]
    assert set(service._tunnels) == {"deployment-1", "deployment-2"}

    service._stop_tunnel("deployment-1")
    assert "deployment-1" not in service._tunnels
    assert "deployment-2" in service._tunnels


def test_stop_all_terminates_both_processes():
    service = CloudflareTunnelService()
    first = make_handle("deployment-1", "https://one.trycloudflare.com")
    second = make_handle("deployment-2", "https://two.trycloudflare.com")
    service._tunnels = {"deployment-1": first, "deployment-2": second}

    service._stop_all()

    assert not service._tunnels
    for handle in (first, second):
        assert handle.port_forward.terminated
        assert handle.cloudflared.terminated
