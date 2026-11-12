import asyncio
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlsplit

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("releasepilot.cloudflare")

QUICK_TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


@dataclass
class TunnelHandle:
    key: str
    namespace: str
    service_name: str
    service_port: int
    local_port: int
    local_url: str
    public_url: Optional[str] = None
    port_forward: Optional[subprocess.Popen] = None
    cloudflared: Optional[subprocess.Popen] = None
    output: List[str] = field(default_factory=list)
    reader: Optional[threading.Thread] = None
    last_verified_at: Optional[str] = None

    @property
    def process_state(self) -> str:
        if self.port_forward is None or self.cloudflared is None:
            return "stopped"
        if self.port_forward.poll() is not None:
            return "port_forward_exited"
        if self.cloudflared.poll() is not None:
            return "cloudflared_exited"
        return "running"


class CloudflareTunnelService:
    """Owns one kubectl/cloudflared process pair per deployment."""

    def __init__(self) -> None:
        self._tunnels: Dict[str, TunnelHandle] = {}
        self._lock = threading.RLock()

    async def ensure_tunnel(
        self,
        deployment_key: str,
        namespace: str,
        service_name: str,
        service_port: int,
        health_path: str,
    ) -> Dict[str, object]:
        return await asyncio.to_thread(
            self._ensure_tunnel,
            deployment_key,
            namespace,
            service_name,
            service_port,
            health_path,
        )

    async def stop_tunnel(self, deployment_key: str) -> None:
        await asyncio.to_thread(self._stop_tunnel, deployment_key)

    async def restart_tunnel(
        self,
        deployment_key: str,
        namespace: str,
        service_name: str,
        service_port: int,
        health_path: str,
    ) -> Dict[str, object]:
        await self.stop_tunnel(deployment_key)
        return await self.ensure_tunnel(
            deployment_key, namespace, service_name, service_port, health_path
        )

    async def stop_all(self) -> None:
        await asyncio.to_thread(self._stop_all)

    def _ensure_tunnel(
        self,
        deployment_key: str,
        namespace: str,
        service_name: str,
        service_port: int,
        health_path: str,
    ) -> Dict[str, object]:
        with self._lock:
            existing = self._tunnels.get(deployment_key)
            if existing and existing.process_state == "running" and existing.public_url:
                if self._verify_url(existing.public_url, health_path):
                    existing.last_verified_at = self._now()
                    return self._result(existing, "ready")
                self._stop_handle(existing)
                self._tunnels.pop(deployment_key, None)

            handle = self._start_handle(
                deployment_key,
                namespace,
                service_name,
                service_port,
            )
            self._tunnels[deployment_key] = handle
            if not self._wait_for_url(handle):
                self._stop_handle(handle)
                self._tunnels.pop(deployment_key, None)
                raise RuntimeError("cloudflared did not provide a Quick Tunnel URL.")
            if not self._wait_for_public_endpoint(handle, health_path):
                self._stop_handle(handle)
                self._tunnels.pop(deployment_key, None)
                raise RuntimeError("The Cloudflare public endpoint did not pass verification.")
            handle.last_verified_at = self._now()
            logger.info(
                "Cloudflare endpoint verified",
                extra={"deployment_id": deployment_key, "service_name": service_name},
            )
            return self._result(handle, "ready")

    def _start_handle(
        self,
        deployment_key: str,
        namespace: str,
        service_name: str,
        service_port: int,
    ) -> TunnelHandle:
        local_port = self._available_port()
        local_url = f"http://{settings.PORT_FORWARD_HOST}:{local_port}"
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kubectl_command = [
            settings.KUBECTL_PATH,
            "port-forward",
            "--address",
            settings.PORT_FORWARD_HOST,
            f"service/{service_name}",
            f"{local_port}:{service_port}",
            "--namespace",
            namespace,
        ]
        try:
            port_forward = subprocess.Popen(
                kubectl_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=flags,
            )
        except (FileNotFoundError, OSError) as exc:
            raise RuntimeError(f"Unable to start kubectl port-forward: {type(exc).__name__}.") from exc
        handle = TunnelHandle(
            key=deployment_key,
            namespace=namespace,
            service_name=service_name,
            service_port=service_port,
            local_port=local_port,
            local_url=local_url,
            port_forward=port_forward,
        )
        handle.reader = self._start_reader(port_forward, handle.output)
        logger.info(
            "Started Kubernetes port-forward",
            extra={"deployment_id": deployment_key, "service_name": service_name},
        )
        if not self._wait_for_local_service(handle):
            self._stop_handle(handle)
            raise RuntimeError("Kubernetes port-forward did not become reachable.")

        try:
            cloudflared = subprocess.Popen(
                [
                    settings.CLOUDFLARED_PATH,
                    "tunnel",
                    "--url",
                    local_url,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=flags,
            )
        except (FileNotFoundError, OSError) as exc:
            self._stop_handle(handle)
            raise RuntimeError(f"Unable to start cloudflared: {type(exc).__name__}.") from exc
        handle.cloudflared = cloudflared
        handle.reader = self._start_reader(cloudflared, handle.output)
        logger.info(
            "Started Cloudflare Quick Tunnel",
            extra={"deployment_id": deployment_key, "service_name": service_name},
        )
        return handle

    @staticmethod
    def _start_reader(process: subprocess.Popen, output: List[str]) -> threading.Thread:
        def read_output() -> None:
            if not process.stdout:
                return
            try:
                for line in process.stdout:
                    output.append(line.strip())
                    if len(output) > 100:
                        del output[:-100]
            except (OSError, ValueError):
                return

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        return reader

    def _wait_for_local_service(self, handle: TunnelHandle) -> bool:
        deadline = time.monotonic() + settings.TUNNEL_STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if handle.port_forward and handle.port_forward.poll() is not None:
                return False
            if self._verify_url(handle.local_url, "/"):
                return True
            time.sleep(0.25)
        return False

    def _wait_for_url(self, handle: TunnelHandle) -> bool:
        deadline = time.monotonic() + settings.TUNNEL_STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if handle.cloudflared and handle.cloudflared.poll() is not None:
                return False
            for line in list(handle.output):
                match = QUICK_TUNNEL_URL.search(line)
                if match:
                    handle.public_url = match.group(0).rstrip("/")
                    logger.info(
                        "Discovered Cloudflare endpoint",
                        extra={"deployment_id": handle.key, "service_name": handle.service_name},
                    )
                    return True
            time.sleep(0.2)
        return False

    

    def _wait_for_public_endpoint(self, handle: TunnelHandle, health_path: str) -> bool:
        if not handle.public_url:
            return False

        timeout = max(
            settings.TUNNEL_PUBLIC_ENDPOINT_TIMEOUT,
            settings.TUNNEL_STARTUP_TIMEOUT,
        )
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if handle.cloudflared and handle.cloudflared.poll() is not None:
                logger.error(
                    "Cloudflared exited before the public endpoint became healthy",
                    extra={"deployment_id": handle.key},
                )
                return False

            if self._verify_url(handle.public_url, health_path):
                logger.info(
                    "Cloudflare public endpoint health verification succeeded",
                    extra={"deployment_id": handle.key},
                )
                return True

            time.sleep(1.0)

        logger.error(
            f"Cloudflare endpoint did not become healthy within {timeout:.0f} seconds: "
            f"{handle.public_url}{health_path}",
            extra={"deployment_id": handle.key},
        )
        return False

    @staticmethod
    def _verify_url(base_url: str, health_path: str) -> bool:
        path = health_path if health_path.startswith("/") else f"/{health_path}"
        try:
            request = urllib.request.Request(
                f"{base_url.rstrip('/')}{path}",
                headers={"User-Agent": "ReleasePilot/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(
                request,
                timeout=settings.ENDPOINT_VERIFICATION_TIMEOUT,
            ) as response:
                return 200 <= response.status < 500
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning(
                f"Endpoint probe to {base_url.rstrip('/')}{path} failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return False



    @staticmethod
    def _available_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((settings.PORT_FORWARD_HOST, 0))
            return int(sock.getsockname()[1])

    def _result(self, handle: TunnelHandle, status: str) -> Dict[str, object]:
        return {
            "status": status,
            "public_url": handle.public_url,
            "local_url": handle.local_url,
            "service_name": handle.service_name,
            "namespace": handle.namespace,
            "service_port": handle.service_port,
            "tunnel_provider": "cloudflare-quick-tunnel",
            "tunnel_process_state": handle.process_state,
            "last_verified_at": handle.last_verified_at,
        }

    def _stop_tunnel(self, deployment_key: str) -> None:
        with self._lock:
            handle = self._tunnels.pop(deployment_key, None)
            if handle:
                self._stop_handle(handle)

    def _stop_all(self) -> None:
        with self._lock:
            handles = list(self._tunnels.values())
            self._tunnels.clear()
            for handle in handles:
                self._stop_handle(handle)

    @staticmethod
    def _stop_handle(handle: TunnelHandle) -> None:
        for process in (handle.cloudflared, handle.port_forward):
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except (subprocess.TimeoutExpired, OSError):
                    try:
                        process.kill()
                        process.wait(timeout=2)
                    except (OSError, subprocess.TimeoutExpired):
                        logger.exception("Unable to stop tunnel child process")
        logger.info(
            "Stopped Cloudflare tunnel processes",
            extra={"deployment_id": handle.key, "service_name": handle.service_name},
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def cleanup_orphaned_processes() -> int:
        """Terminate any orphaned cloudflared or kubectl port-forward processes from previous crashed sessions."""
        import sys
        if sys.platform != "win32":
            return 0
        cleaned = 0
        try:
            cmd = (
                "Get-CimInstance Win32_Process -Filter \"Name = 'cloudflared.exe'\" "
                "| Where-Object { $_.CommandLine -like '*tunnel*' } "
                "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"
            )
            res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=10)
            pids = [line.strip() for line in res.stdout.splitlines() if line.strip().isdigit()]
            cleaned += len(pids)
            if pids:
                logger.info(f"Cleaned up {len(pids)} orphaned cloudflared process(es): {pids}")
        except Exception as exc:
            logger.warning(f"Could not sweep orphaned cloudflared processes: {exc}")

        try:
            cmd = (
                "Get-CimInstance Win32_Process -Filter \"Name = 'kubectl.exe'\" "
                "| Where-Object { $_.CommandLine -like '*port-forward*' } "
                "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"
            )
            res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=10)
            pids = [line.strip() for line in res.stdout.splitlines() if line.strip().isdigit()]
            cleaned += len(pids)
            if pids:
                logger.info(f"Cleaned up {len(pids)} orphaned kubectl port-forward process(es): {pids}")
        except Exception as exc:
            logger.warning(f"Could not sweep orphaned kubectl processes: {exc}")

        return cleaned


cloudflare_tunnel_service = CloudflareTunnelService()
