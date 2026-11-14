import pytest
from concurrent.futures import ThreadPoolExecutor
import time

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
        self.stdout = None

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


def test_new_tunnel_is_not_ready_until_public_health_check_passes(monkeypatch):
    service = CloudflareTunnelService()
    handle = make_handle(
        "deployment-startup",
        "https://new-name.trycloudflare.com",
    )
    starts = []
    monkeypatch.setattr(
        service,
        "_start_handle",
        lambda *args: starts.append(args) or handle,
    )
    monkeypatch.setattr(service, "_verify_url", lambda url, path: True)

    result = service._ensure_tunnel(
        handle.key,
        handle.namespace,
        handle.service_name,
        handle.service_port,
        "/healthz",
    )

    assert starts
    assert result["status"] == "ready"
    assert result["public_url"] == handle.public_url
    assert result["tunnel_process_state"] == "running"


def test_public_endpoint_retries_dns_propagation(monkeypatch):
    service = CloudflareTunnelService()
    handle = make_handle("deployment-dns", "https://sample.trycloudflare.com")
    attempts = 0

    def verify(url, path):
        nonlocal attempts
        attempts += 1
        return attempts >= 3

    monkeypatch.setattr(service, "_verify_url", verify)
    monkeypatch.setattr(settings, "TUNNEL_STARTUP_TIMEOUT", 0.1)
    monkeypatch.setattr(settings, "TUNNEL_PUBLIC_ENDPOINT_TIMEOUT", 1)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    assert service._wait_for_public_endpoint(handle, "/healthz")
    assert attempts == 3


def test_public_endpoint_verification_times_out(monkeypatch):
    service = CloudflareTunnelService()
    handle = make_handle("deployment-unhealthy", "https://sample.trycloudflare.com")
    monkeypatch.setattr(service, "_verify_url", lambda url, path: False)
    monkeypatch.setattr(settings, "TUNNEL_STARTUP_TIMEOUT", 0.02)
    monkeypatch.setattr(settings, "TUNNEL_PUBLIC_ENDPOINT_TIMEOUT", 0.02)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    assert not service._wait_for_public_endpoint(handle, "/healthz")


@pytest.mark.parametrize("status_code", [200, 201, 202, 204])
def test_http_2xx_passes_health_verification(monkeypatch, status_code):
    class SuccessResponse:
        status = status_code

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "app.services.cloudflare_tunnel.urllib.request.urlopen",
        lambda *args, **kwargs: SuccessResponse(),
    )

    assert CloudflareTunnelService._verify_url(
        "https://sample.trycloudflare.com", "/healthz"
    )


def test_http_404_does_not_pass_health_verification(monkeypatch):
    class NotFoundResponse:
        status = 404

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "app.services.cloudflare_tunnel.urllib.request.urlopen",
        lambda *args, **kwargs: NotFoundResponse(),
    )

    assert not CloudflareTunnelService._verify_url(
        "https://sample.trycloudflare.com", "/healthz"
    )


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

    with pytest.raises(RuntimeError, match="Quick Tunnel URL") as error:
        service._ensure_tunnel(
            handle.key,
            handle.namespace,
            handle.service_name,
            handle.service_port,
            "/healthz",
        )

    assert "exit code 1" in str(error.value)
    assert handle.port_forward.terminated
    assert handle.cloudflared.poll() is not None


def test_port_forward_exit_aborts_public_health_verification(monkeypatch):
    service = CloudflareTunnelService()
    handle = make_handle("deployment-port-forward-exit", "https://sample.trycloudflare.com")
    handle.port_forward.returncode = 1

    assert not service._wait_for_public_endpoint(handle, "/healthz")


def test_cloudflare_public_health_failure_returns_actionable_error(monkeypatch):
    service = CloudflareTunnelService()
    handle = make_handle("deployment-public-unhealthy", "https://sample.trycloudflare.com")
    monkeypatch.setattr(service, "_start_handle", lambda *args: handle)
    monkeypatch.setattr(service, "_verify_url", lambda url, path: False)
    monkeypatch.setattr(settings, "TUNNEL_PUBLIC_ENDPOINT_TIMEOUT", 0.01)
    monkeypatch.setattr(settings, "TUNNEL_STARTUP_TIMEOUT", 0.01)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="DNS resolution or the public health check"):
        service._ensure_tunnel(
            handle.key,
            handle.namespace,
            handle.service_name,
            handle.service_port,
            "/healthz",
        )

    assert handle.key not in service._tunnels
    assert handle.port_forward.terminated
    assert handle.cloudflared.terminated


def test_start_handle_uses_configured_kubectl_and_cloudflared_commands(monkeypatch):
    service = CloudflareTunnelService()
    started_commands = []

    def fake_popen(command, **kwargs):
        started_commands.append(command)
        return FakeProcess()

    monkeypatch.setattr("app.services.cloudflare_tunnel.subprocess.Popen", fake_popen)
    monkeypatch.setattr(service, "_available_port", lambda: 41234)
    monkeypatch.setattr(service, "_wait_for_local_service", lambda *args: True)

    handle = service._start_handle(
        "deployment-command",
        "registration-login-staging",
        "registration-login",
        3000,
        "/healthz",
    )

    assert started_commands[0] == [
        settings.KUBECTL_PATH,
        "port-forward",
        "--address",
        settings.PORT_FORWARD_HOST,
        "service/registration-login",
        "41234:3000",
        "--namespace",
        "registration-login-staging",
    ]
    assert started_commands[1] == [
        settings.CLOUDFLARED_PATH,
        "tunnel",
        "--url",
        "http://127.0.0.1:41234",
    ]
    service._stop_handle(handle)


def test_multiple_deployments_have_isolated_tunnels(monkeypatch):
    service = CloudflareTunnelService()
    handles = {}

    def start_handle(key, namespace, service_name, service_port, health_path):
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


def test_running_tunnel_is_reused_without_starting_another(monkeypatch):
    service = CloudflareTunnelService()
    existing = make_handle("deployment-reused", "https://same.trycloudflare.com")
    service._tunnels[existing.key] = existing
    monkeypatch.setattr(service, "_verify_url", lambda url, path: True)
    monkeypatch.setattr(
        service,
        "_start_handle",
        lambda *args: pytest.fail("A healthy tunnel must be reused."),
    )

    result = service._ensure_tunnel(
        existing.key, existing.namespace, existing.service_name, 80, "/healthz"
    )

    assert result["public_url"] == existing.public_url


def test_exited_tunnel_process_pair_is_cleaned_before_restart(monkeypatch):
    service = CloudflareTunnelService()
    old_handle = make_handle(
        "deployment-restart",
        "https://old.trycloudflare.com",
        cloudflared_code=1,
    )
    new_handle = make_handle(
        "deployment-restart",
        "https://new.trycloudflare.com",
    )
    service._tunnels[old_handle.key] = old_handle
    monkeypatch.setattr(service, "_start_handle", lambda *args: new_handle)
    monkeypatch.setattr(service, "_verify_url", lambda url, path: True)

    result = service._ensure_tunnel(
        old_handle.key, old_handle.namespace, old_handle.service_name, 80, "/healthz"
    )

    assert result["public_url"] == new_handle.public_url
    assert old_handle.port_forward.terminated


def test_concurrent_endpoint_requests_start_only_one_tunnel(monkeypatch):
    service = CloudflareTunnelService()
    started = []

    def start_handle(key, namespace, service_name, service_port, health_path):
        started.append(key)
        time.sleep(0.02)
        return make_handle(key, f"https://{key}.trycloudflare.com")

    monkeypatch.setattr(service, "_start_handle", start_handle)
    monkeypatch.setattr(service, "_verify_url", lambda url, path: True)

    def ensure():
        return service._ensure_tunnel(
            "deployment-concurrent", "ns", "service", 80, "/healthz"
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: ensure(), range(5)))

    assert len(started) == 1
    assert all(result["status"] == "ready" for result in results)


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
