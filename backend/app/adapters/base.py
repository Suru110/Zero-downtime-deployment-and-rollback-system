from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class AdapterResult(BaseModel):
    success: bool
    is_simulated: bool
    adapter_name: str
    message: str
    details: Dict[str, Any] = {}
    logs: List[Dict[str, Any]] = []

class BaseDeploymentAdapter(ABC):
    @property
    @abstractmethod
    def adapter_name(self) -> str:
        pass

    @property
    @abstractmethod
    def is_simulated(self) -> bool:
        pass

    @abstractmethod
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
        """Trigger a zero-downtime deployment."""
        pass

    @abstractmethod
    async def rollback(
        self,
        app_name: str,
        namespace: str,
        target_image: str,
        replicas: int
    ) -> AdapterResult:
        """Rollback to a previous known-good image/state."""
        pass

    @abstractmethod
    async def get_pod_status(self, app_name: str, namespace: str) -> Dict[str, Any]:
        """Fetch live pod readiness and count."""
        pass

class BaseSecurityScannerAdapter(ABC):
    @property
    @abstractmethod
    def adapter_name(self) -> str:
        pass

    @property
    @abstractmethod
    def is_simulated(self) -> bool:
        pass

    @abstractmethod
    async def scan_image(self, image_ref: str) -> Dict[str, Any]:
        """Scan container image for vulnerabilities."""
        pass

class BaseGitOpsAdapter(ABC):
    @property
    @abstractmethod
    def adapter_name(self) -> str:
        pass

    @property
    @abstractmethod
    def is_simulated(self) -> bool:
        pass

    @abstractmethod
    async def sync_application(self, app_name: str, revision: str) -> AdapterResult:
        """Trigger Argo CD sync."""
        pass

class BaseMetricsAdapter(ABC):
    @property
    @abstractmethod
    def adapter_name(self) -> str:
        pass

    @property
    @abstractmethod
    def is_simulated(self) -> bool:
        pass

    @abstractmethod
    async def query_error_rate(self, app_name: str, namespace: str) -> float:
        """Query HTTP 5xx error percentage."""
        pass

    @abstractmethod
    async def get_telemetry(self, app_name: str, namespace: str) -> Dict[str, Any]:
        """Fetch CPU, memory, request volume metrics."""
        pass
