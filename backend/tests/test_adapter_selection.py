import pytest

from app.adapters import get_deployment_adapter
from app.adapters.k8s.mock_adapter import MockKubernetesAdapter
from app.adapters.k8s.production_adapter import ProductionKubernetesAdapter
from app.core.config import settings


def test_mock_adapter_requires_explicit_mock_mode(monkeypatch):
    monkeypatch.setattr(settings, "KUBERNETES_MODE", "mock")

    adapter = get_deployment_adapter()

    assert isinstance(adapter, MockKubernetesAdapter)
    assert adapter.is_simulated


def test_production_mode_selects_real_adapter_even_when_mock_adapters_enabled(
    monkeypatch,
):
    monkeypatch.setattr(settings, "KUBERNETES_MODE", "production")
    monkeypatch.setattr(settings, "ENABLE_MOCK_ADAPTERS", True)
    monkeypatch.setattr(
        ProductionKubernetesAdapter, "_init_client", lambda self: None
    )

    adapter = get_deployment_adapter()

    assert isinstance(adapter, ProductionKubernetesAdapter)
    assert not adapter.is_simulated


def test_production_adapter_is_not_replaced_when_cluster_initialization_fails(
    monkeypatch,
):
    monkeypatch.setattr(settings, "KUBERNETES_MODE", "production")

    def fail_initialization(adapter):
        adapter._k8s_client = None
        adapter._core_client = None
        adapter.initialization_error = "Kubernetes client initialization failed."

    monkeypatch.setattr(
        ProductionKubernetesAdapter, "_init_client", fail_initialization
    )

    adapter = get_deployment_adapter()

    assert isinstance(adapter, ProductionKubernetesAdapter)
    assert not adapter.is_simulated
    assert adapter.initialization_error


def test_unknown_kubernetes_mode_fails_instead_of_falling_back(monkeypatch):
    monkeypatch.setattr(settings, "KUBERNETES_MODE", "unexpected")

    with pytest.raises(ValueError, match="KUBERNETES_MODE"):
        get_deployment_adapter()
