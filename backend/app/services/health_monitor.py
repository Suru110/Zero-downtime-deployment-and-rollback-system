import time
from typing import Dict, Any

import httpx
from sqlalchemy.orm import Session

from app.adapters import get_deployment_adapter, get_metrics_adapter
from app.core.config import settings
from app.core.logging import get_logger
from app.models.deployment import Deployment
from app.models.environment import Environment
from app.models.health_check import HealthCheck
from app.models.project import Project
from app.core.metrics import HEALTH_CHECKS

logger = get_logger("releasepilot.health")


class HealthMonitorService:
    @staticmethod
    def _record(db: Session, deployment_id: str, check_type: str, status: str,
                status_code: int | None, latency_ms: float, details: Dict[str, Any]) -> None:
        db.add(HealthCheck(
            deployment_id=deployment_id,
            check_type=check_type,
            status=status,
            status_code=status_code,
            latency_ms=latency_ms,
            details=details,
        ))
        db.commit()
        HEALTH_CHECKS.labels(check_type, status, str(details.get("is_simulated", False)).lower()).inc()

    @classmethod
    async def verify_deployment(
        cls, db: Session, deployment: Deployment, environment: Environment,
        project: Project, simulate_failure: bool = False
    ) -> bool:
        """Run bounded readiness, HTTP smoke, and metrics checks.

        A simulated adapter does not make an HTTP request because no application
        endpoint exists in the mock cluster. Production adapters always perform
        the configured HTTP check and report failures truthfully.
        """
        adapter = get_deployment_adapter()
        all_passed = True

        started = time.monotonic()
        readiness_status = "failed" if simulate_failure else "passed"
        readiness_details: Dict[str, Any] = {
            "strategy": deployment.strategy,
            "target_namespace": environment.k8s_namespace,
            "is_simulated": adapter.is_simulated,
        }
        if not adapter.is_simulated and not simulate_failure:
            pod_status = await adapter.get_pod_status(project.name, environment.k8s_namespace)
            readiness_details["pod_status"] = pod_status
            ready = pod_status.get("ready_replicas", 0)
            desired = pod_status.get("desired_replicas", environment.replicas)
            if ready < desired:
                readiness_status = "failed"
                readiness_details["error"] = "Rollout readiness did not reach the desired replica count."
        if simulate_failure:
            readiness_details["error"] = "Readiness verification was requested to fail."
        cls._record(
            db, deployment.id, "readiness_probe", readiness_status,
            200 if readiness_status == "passed" else 503,
            round((time.monotonic() - started) * 1000, 2), readiness_details,
        )
        if readiness_status != "passed":
            return False

        smoke_started = time.monotonic()
        smoke_status = "failed"
        smoke_code = None
        smoke_details: Dict[str, Any] = {
            "endpoint": environment.smoke_test_endpoint or project.health_path,
            "expected_status": environment.smoke_test_expected_status,
            "timeout_seconds": environment.smoke_test_timeout_seconds,
            "attempts": environment.verification_attempts,
            "is_simulated": adapter.is_simulated,
        }
        if adapter.is_simulated:
            smoke_status = "failed" if simulate_failure else "passed"
            smoke_code = environment.smoke_test_expected_status if smoke_status == "passed" else 503
            if smoke_status == "failed":
                smoke_details["error"] = "Simulated smoke test failure."
        else:
            url = environment.smoke_test_endpoint or project.health_path
            service_health_check = getattr(adapter, "check_service_health", None)
            for attempt in range(1, environment.verification_attempts + 1):
                try:
                    if callable(service_health_check) and not url.startswith(("http://", "https://")):
                        smoke_code = await service_health_check(
                            project.name,
                            environment.k8s_namespace,
                            url,
                        )
                    else:
                        if not url.startswith(("http://", "https://")):
                            port_suffix = f":{project.default_port}" if project.default_port and project.default_port != 80 else ""
                            url = f"http://{project.name}.{environment.k8s_namespace}.svc.cluster.local{port_suffix}{url}"
                        async with httpx.AsyncClient(timeout=environment.smoke_test_timeout_seconds) as client:
                            response = await client.get(url)
                        smoke_code = response.status_code
                    smoke_details["attempt"] = attempt
                    if smoke_code == environment.smoke_test_expected_status:
                        smoke_status = "passed"
                        break
                    smoke_details["error"] = f"Expected HTTP {environment.smoke_test_expected_status}; received HTTP {smoke_code}."
                except httpx.TimeoutException:
                    smoke_details["error"] = "Smoke test timed out."
                except httpx.HTTPError:
                    smoke_details["error"] = "Smoke test request failed."
                except Exception as exc:
                    smoke_details["error"] = f"Kubernetes service health check failed: {type(exc).__name__}."
                if attempt < environment.verification_attempts:
                    await __import__("asyncio").sleep(min(1.0, environment.smoke_test_timeout_seconds / 2))
        cls._record(
            db, deployment.id, "smoke_test", smoke_status, smoke_code,
            round((time.monotonic() - smoke_started) * 1000, 2), smoke_details,
        )
        if smoke_status != "passed":
            all_passed = False

        metrics_started = time.monotonic()
        error_rate = await get_metrics_adapter().query_error_rate(project.name, environment.k8s_namespace)
        metrics_passed = error_rate < 1.0
        cls._record(
            db, deployment.id, "metric_error_rate", "passed" if metrics_passed else "failed",
            200, round((time.monotonic() - metrics_started) * 1000, 2),
            {"error_rate_pct": error_rate, "threshold_pct": 1.0},
        )
        return all_passed and metrics_passed
