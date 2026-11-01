from app.core.config import settings
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

def get_deployment_adapter() -> BaseDeploymentAdapter:
    if settings.ENABLE_MOCK_ADAPTERS:
        return MockKubernetesAdapter()
    return ProductionKubernetesAdapter()

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
