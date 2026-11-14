from app.core.config import settings
from typing import Optional
from app.adapters.base import (
    BaseDeploymentAdapter,
    BaseSecurityScannerAdapter,
    BaseGitOpsAdapter,
    BaseMetricsAdapter
)
from app.adapters.k8s.mock_adapter import MockKubernetesAdapter
from app.adapters.k8s.production_adapter import ProductionKubernetesAdapter
from app.adapters.scanner.mock_trivy_adapter import MockTrivyScannerAdapter
from app.adapters.scanner.trivy_adapter import ProductionTrivyScannerAdapter
from app.adapters.gitops.mock_argo_adapter import MockArgoCDAdapter
from app.adapters.gitops.argo_adapter import ProductionArgoCDAdapter
from app.adapters.monitoring.mock_prometheus_adapter import MockPrometheusAdapter
from app.adapters.monitoring.prometheus_adapter import ProductionPrometheusAdapter

def get_deployment_adapter(mode: Optional[str] = None) -> BaseDeploymentAdapter:
    selected_mode = (mode or settings.KUBERNETES_MODE).strip().lower()
    if selected_mode == "mock":
        return MockKubernetesAdapter()
    if selected_mode == "production":
        return ProductionKubernetesAdapter()
    raise ValueError(
        "KUBERNETES_MODE must be either 'production' or 'mock'; "
        f"received '{selected_mode}'."
    )

def get_security_scanner_adapter() -> BaseSecurityScannerAdapter:
    if settings.ENABLE_MOCK_ADAPTERS:
        return MockTrivyScannerAdapter()
    return ProductionTrivyScannerAdapter()

def get_gitops_adapter() -> BaseGitOpsAdapter:
    if settings.ENABLE_MOCK_ADAPTERS:
        return MockArgoCDAdapter()
    return ProductionArgoCDAdapter()

def get_metrics_adapter() -> BaseMetricsAdapter:
    if settings.ENABLE_MOCK_ADAPTERS:
        return MockPrometheusAdapter()
    return ProductionPrometheusAdapter()
