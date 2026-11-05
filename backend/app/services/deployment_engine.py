import asyncio
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.deployment import Deployment
from app.models.environment import Environment
from app.models.project import Project
from app.models.release import Release
from app.adapters import get_deployment_adapter, get_security_scanner_adapter
from app.services.health_monitor import HealthMonitorService
from app.services.rollback_manager import RollbackManager
from app.services.audit_service import AuditService
from app.core.logging import get_logger
from app.core.config import settings
from app.core.kubernetes import normalize_kubernetes_name
from app.core.metrics import (
    DEPLOYMENT_DURATION, ROLLOUT_FAILURES,
)

logger = get_logger("releasepilot.deployment")

class DeploymentEngine:
    @staticmethod
    def _append_log(logs: List[Dict[str, Any]], level: str, message: str) -> None:
        logs.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message
        })

    @classmethod
    def _finalize_failed_deployment(
        cls,
        deployment: Deployment,
        logs: List[Dict[str, Any]],
        deployment_started: datetime,
    ) -> None:
        deployment.status = "failed"
        deployment.finished_at = datetime.utcnow()
        deployment.logs = logs
        DEPLOYMENT_DURATION.labels(
            deployment.strategy, deployment.status
        ).observe((deployment.finished_at - deployment_started).total_seconds())

    @classmethod
    async def _wait_if_paused(
        cls,
        db: Session,
        deployment: Deployment,
    ) -> List[Dict[str, Any]]:
        while True:
            db.refresh(deployment)
            if not (deployment.metadata_info or {}).get("paused"):
                return list(deployment.logs or [])
            await asyncio.sleep(1)

    @classmethod
    async def execute_deployment(
        cls,
        db: Session,
        deployment_id: str,
        simulate_failure: bool = False
    ) -> None:
        """
        Asynchronously drives the end-to-end zero-downtime deployment pipeline:
        Phase 1: Scanning (Trivy CVE analysis)
        Phase 2: Deploying (Kubernetes Rolling/Canary Rollout)
        Phase 3: Verifying (Readiness probe, smoke test, metric validation)
        Phase 4: Finalize Active OR Automated Rollback upon verification failure
        """
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            logger.error(f"Deployment {deployment_id} not found")
            return
        if deployment.status in {"active", "rolled_back", "failed", "cancelled"}:
            logger.info("Deployment %s is already terminal with status %s", deployment_id, deployment.status)
            return
        deployment_started = datetime.utcnow()
        logger.info(
            "Deployment execution started",
            extra={"deployment_id": deployment.id, "extra": {
                "project_id": deployment.project_id,
                "environment_id": deployment.environment_id,
            }},
        )

        environment = db.query(Environment).filter(Environment.id == deployment.environment_id).first()
        project = db.query(Project).filter(Project.id == deployment.project_id).first()
        release = db.query(Release).filter(Release.id == deployment.release_id).first()
        original_namespace = environment.k8s_namespace
        normalized_namespace = normalize_kubernetes_name(original_namespace)
        namespace_was_normalized = normalized_namespace != original_namespace
        if namespace_was_normalized:
            environment.k8s_namespace = normalized_namespace
            db.commit()

        logs: List[Dict[str, Any]] = list(deployment.logs or [])
        if namespace_was_normalized:
            cls._append_log(
                logs,
                "WARN",
                f"Normalized environment namespace '{original_namespace}' to '{normalized_namespace}'.",
            )
        logs = await cls._wait_if_paused(db, deployment)
        cls._append_log(logs, "INFO", f"Starting deployment pipeline for '{project.name}' -> environment '{environment.name}'")
        image_reference = release.image_reference or f"{project.image_repository}:{release.image_tag}"
        cls._append_log(logs, "INFO", f"Target release: {release.version} (Image: {image_reference})")

        # Phase 0: Pre-flight validation
        cls._append_log(logs, "INFO", "Running pre-flight environment and configuration validations...")
        if not (1 <= project.default_port <= 65535):
            cls._append_log(logs, "ERROR", f"Pre-flight failed: Invalid configured port {project.default_port}.")
            cls._finalize_failed_deployment(deployment, logs, deployment_started)
            db.commit()
            return

        if not release.image_reference and not (project.image_repository and release.image_tag):
            cls._append_log(logs, "ERROR", "Pre-flight failed: Release image reference cannot be resolved.")
            cls._finalize_failed_deployment(deployment, logs, deployment_started)
            db.commit()
            return

        k8s_adapter = get_deployment_adapter()
        if not k8s_adapter.is_simulated and not getattr(k8s_adapter, "_k8s_client", None):
            cls._append_log(logs, "ERROR", "Pre-flight failed: Kubernetes cluster unreachable. Real cluster mode is active but connection failed.")
            cls._finalize_failed_deployment(deployment, logs, deployment_started)
            db.commit()
            return

        cls._append_log(logs, "INFO", "Pre-flight validations passed successfully.")

        deployment.status = "scanning"
        deployment.progress = 15
        deployment.logs = logs
        db.commit()

        # Phase 1: Security Scanning
        logs = await cls._wait_if_paused(db, deployment)
        scanner = get_security_scanner_adapter()
        cls._append_log(logs, "INFO", f"Executing container image security scan via adapter '{scanner.adapter_name}'")
        scan_report = await scanner.scan_image(image_reference)
        
        # Update release scan info
        release.scan_status = scan_report.get("status", "clean")
        release.scan_results = scan_report
        db.commit()

        if scan_report.get("critical_count", 0) > 0 and environment.name == "production":
            cls._append_log(logs, "ERROR", f"CRITICAL security vulnerabilities found in image. Deployment halted by policy.")
            deployment.status = "failed"
            deployment.finished_at = datetime.utcnow()
            deployment.logs = logs
            db.commit()
            return

        cls._append_log(logs, "INFO", f"Security scan passed: {scan_report.get('critical_count', 0)} Critical, {scan_report.get('high_count', 0)} High CVEs.")

        # Phase 2: Deploying
        logs = await cls._wait_if_paused(db, deployment)
        deployment.status = "deploying"
        deployment.progress = 40
        deployment.logs = logs
        db.commit()

        k8s_adapter = get_deployment_adapter()
        deployment.adapter_name = k8s_adapter.adapter_name
        deployment.is_simulated = k8s_adapter.is_simulated

        cls._append_log(logs, "INFO", f"Dispatching deployment to orchestrator '{k8s_adapter.adapter_name}' (simulated={k8s_adapter.is_simulated})")

        deployment_env = dict(environment.env_vars or {})
        deployment_env.setdefault("HEALTH_PATH", project.health_path)
        deploy_result = await k8s_adapter.deploy(
            app_name=project.name,
            namespace=environment.k8s_namespace,
            image=image_reference,
            replicas=environment.replicas,
            port=project.default_port,
            env_vars=deployment_env,
            strategy=deployment.strategy,
            canary_steps=environment.canary_steps,
            simulate_failure=simulate_failure,
            health_path=project.health_path,
        )

        adapter_public_url = deploy_result.details.get("public_url")
        deployment.metadata_info = {
            **(deployment.metadata_info or {}),
            **({"public_url": adapter_public_url} if adapter_public_url else {}),
            "endpoint_status": deploy_result.details.get("endpoint_status", "unavailable"),
            **({"endpoint_error": deploy_result.details["endpoint_error"]} if deploy_result.details.get("endpoint_error") else {}),
            "adapter_details": deploy_result.details,
        }
        logs.extend(deploy_result.logs)
        deployment.logs = logs

        if not deploy_result.success:
            ROLLOUT_FAILURES.labels(
                deploy_result.adapter_name, str(deploy_result.is_simulated).lower()
            ).inc()
            error_detail = deploy_result.details.get("error") if deploy_result.details else None
            failure_message = deploy_result.message
            if error_detail:
                failure_message = f"{failure_message} ({error_detail})"
            cls._append_log(logs, "ERROR", f"Deployment execution failed: {failure_message}")
            if environment.auto_rollback_enabled and not (
                settings.APP_ENV == "production" and deployment.is_simulated
            ):
                cls._append_log(logs, "WARN", "Auto-rollback enabled. Triggering immediate rollback...")
                db.commit()
                try:
                    await RollbackManager.trigger_rollback(
                        db=db,
                        deployment=deployment,
                        reason=f"Deployment phase failure: {failure_message}",
                        is_automated=True
                    )
                except ValueError as exc:
                    cls._append_log(logs, "WARN", f"Automatic rollback was not run: {exc}")
                    cls._finalize_failed_deployment(deployment, logs, deployment_started)
                    db.commit()
            else:
                cls._finalize_failed_deployment(deployment, logs, deployment_started)
                db.commit()
            return

        # Phase 3: Verifying (Synthetic Health Checks)
        logs = await cls._wait_if_paused(db, deployment)
        deployment.status = "verifying"
        deployment.progress = 75
        deployment.logs = logs
        db.commit()

        cls._append_log(logs, "INFO", "Initiating post-deployment synthetic verification (Readiness + Smoke + Metrics)...")
        try:
            health_passed = await asyncio.wait_for(
                HealthMonitorService.verify_deployment(
                    db=db,
                    deployment=deployment,
                    environment=environment,
                    project=project,
                    simulate_failure=simulate_failure,
                ),
                timeout=environment.verification_timeout_seconds,
            )
        except asyncio.TimeoutError:
            cls._append_log(logs, "ERROR", "Verification timed out before all required checks completed.")
            deployment.status = "failed"
            deployment.finished_at = datetime.utcnow()
            DEPLOYMENT_DURATION.labels(
                deployment.strategy, deployment.status
            ).observe((deployment.finished_at - deployment_started).total_seconds())
            deployment.logs = logs
            db.commit()
            if environment.auto_rollback_enabled and not (
                settings.APP_ENV == "production" and deployment.is_simulated
            ):
                try:
                    await RollbackManager.trigger_rollback(
                        db=db,
                        deployment=deployment,
                        reason="Deployment verification timed out",
                        is_automated=True,
                    )
                except ValueError as exc:
                    cls._append_log(logs, "WARN", f"Automatic rollback was not run: {exc}")
                    db.commit()
            return

        if not health_passed:
            cls._append_log(logs, "ERROR", "Health verification failed! Endpoint response unhealthy or error SLA breached.")
            if environment.auto_rollback_enabled and not (
                settings.APP_ENV == "production" and deployment.is_simulated
            ):
                cls._append_log(logs, "WARN", "Auto-rollback policy triggered by verification failure.")
                db.commit()
                try:
                    await RollbackManager.trigger_rollback(
                        db=db,
                        deployment=deployment,
                        reason="Synthetic health check or smoke test failed post-deployment",
                        is_automated=True
                    )
                except ValueError as exc:
                    cls._append_log(logs, "WARN", f"Automatic rollback was not run: {exc}")
                    cls._finalize_failed_deployment(deployment, logs, deployment_started)
                    db.commit()
            else:
                cls._finalize_failed_deployment(deployment, logs, deployment_started)
                db.commit()
            return

        # Phase 4: Finalize Active
        cls._append_log(logs, "INFO", f"All health checks passed! Promoting release '{release.version}' to ACTIVE in '{environment.name}'.")
        deployment.status = "active"
        deployment.progress = 100
        deployment.finished_at = datetime.utcnow()
        deployment.logs = logs
        DEPLOYMENT_DURATION.labels(
            deployment.strategy, deployment.status
        ).observe((deployment.finished_at - deployment_started).total_seconds())

        # Update environment's active release
        environment.current_release_id = release.id
        db.commit()

        # Audit success
        AuditService.log_event(
            db=db,
            action="deployment.success",
            entity_type="deployment",
            entity_id=deployment.id,
            details={
                "project": project.name,
                "environment": environment.name,
                "release": release.version,
                "strategy": deployment.strategy
            }
        )
