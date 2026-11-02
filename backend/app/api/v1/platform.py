from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters import (
    get_deployment_adapter,
    get_gitops_adapter,
    get_metrics_adapter,
    get_security_scanner_adapter,
)
from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.user import User
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/platform", tags=["Platform Health"])


def _check_k8s_connectivity() -> dict:
    """Attempt to reach the configured Kubernetes cluster and return status."""
    if settings.ENABLE_MOCK_ADAPTERS:
        return {
            "connected": False,
            "mode": "simulation",
            "reason": (
                "ENABLE_MOCK_ADAPTERS=true – set to false and provide a valid "
                "kubeconfig to enable real Kubernetes operations."
            ),
        }
    try:
        import os
        from kubernetes import client, config

        if settings.KUBERNETES_IN_CLUSTER:
            config.load_incluster_config()
        elif settings.KUBECONFIG_PATH and os.path.exists(
            os.path.expanduser(settings.KUBECONFIG_PATH)
        ):
            config.load_kube_config(
                config_file=os.path.expanduser(settings.KUBECONFIG_PATH)
            )
        else:
            config.load_kube_config()

        version_api = client.VersionApi()
        info = version_api.get_code()
        return {
            "connected": True,
            "mode": "real",
            "server_version": f"{info.major}.{info.minor}",
        }
    except Exception as exc:
        return {
            "connected": False,
            "mode": "real",
            "reason": (
                f"Kubernetes cluster unreachable: {type(exc).__name__}. "
                "Verify KUBECONFIG_PATH or ensure minikube/kind is running."
            ),
        }


@router.get("/health", response_model=ApiResponse[dict])
async def platform_health(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    deployment_adapter = get_deployment_adapter()
    gitops_adapter = get_gitops_adapter()
    metrics_adapter = get_metrics_adapter()
    scanner_adapter = get_security_scanner_adapter()

    all_simulated = all(
        a.is_simulated
        for a in [deployment_adapter, gitops_adapter, metrics_adapter, scanner_adapter]
    )

    k8s_status = _check_k8s_connectivity()

    return ApiResponse(
        success=True,
        data={
            "status": "ok",
            "adapter_mode": "simulation" if all_simulated else "real",
            "simulation_active": all_simulated,
            "simulation_warning": (
                "All adapters are running in SIMULATION mode. "
                "No real Kubernetes operations are performed. "
                "Set ENABLE_MOCK_ADAPTERS=false to switch to real infrastructure."
                if all_simulated
                else None
            ),
            "kubernetes": k8s_status,
            "integrations": {
                deployment_adapter.adapter_name: {
                    "type": "kubernetes",
                    "configured": True,
                    "is_simulated": deployment_adapter.is_simulated,
                },
                gitops_adapter.adapter_name: {
                    "type": "gitops",
                    "configured": True,
                    "is_simulated": gitops_adapter.is_simulated,
                },
                metrics_adapter.adapter_name: {
                    "type": "metrics",
                    "configured": True,
                    "is_simulated": metrics_adapter.is_simulated,
                },
                scanner_adapter.adapter_name: {
                    "type": "scanner",
                    "configured": True,
                    "is_simulated": scanner_adapter.is_simulated,
                },
            },
        },
    )
