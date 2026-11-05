from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.deployment import Deployment
from app.models.environment import Environment
from app.models.release import Release
from app.models.rollback import RollbackEvent
from app.adapters import get_deployment_adapter
from app.services.audit_service import AuditService
from app.services.health_monitor import HealthMonitorService
from app.core.metrics import ROLLBACKS
from app.core.metrics import DEPLOYMENT_DURATION
from app.core.logging import get_logger
from app.core.kubernetes import normalize_kubernetes_name

logger = get_logger("releasepilot.rollback")

class RollbackManager:
    @staticmethod
    async def trigger_rollback(
        db: Session,
        deployment: Deployment,
        reason: str,
        is_automated: bool = True,
        triggered_by_user_id: Optional[str] = None,
        username: Optional[str] = None
    ) -> RollbackEvent:
        """
        Executes atomic rollback of a deployment to the last known-good release.
        """
        environment = db.query(Environment).filter(Environment.id == deployment.environment_id).first()
        if not environment:
            raise ValueError("Target environment not found")
        conflict = db.query(Deployment).filter(
            Deployment.environment_id == environment.id,
            Deployment.id != deployment.id,
            Deployment.status.in_(("pending", "scanning", "deploying", "verifying", "rolling_back")),
        ).first()
        if conflict:
            raise ValueError("Another deployment or rollback is already in progress for this environment")

        # Determine target release to restore
        restored_release = None
        if environment.current_release_id and environment.current_release_id != deployment.release_id:
            restored_release = db.query(Release).filter(Release.id == environment.current_release_id).first()
        
        # If current_release_id matches or was empty, find the last successful release
        if not restored_release:
            prev_success_dep = (
                db.query(Deployment)
                .filter(
                    Deployment.environment_id == environment.id,
                    Deployment.status == "active",
                    Deployment.release_id != deployment.release_id
                )
                .order_by(Deployment.started_at.desc())
                .first()
            )
            if prev_success_dep:
                restored_release = db.query(Release).filter(Release.id == prev_success_dep.release_id).first()

        if not restored_release:
            raise ValueError("No previous release available for rollback")

        project = environment.project
        k8s_adapter = get_deployment_adapter()

        logger.warning(
            f"INITIATING ROLLBACK: Dep={deployment.id} TargetRelease={restored_release.version} Reason='{reason}'",
            extra={"deployment_id": deployment.id},
        )

        rollback_record = RollbackEvent(
            source_deployment_id=deployment.id,
            environment_id=environment.id,
            failed_release_id=deployment.release_id,
            restored_release_id=restored_release.id,
            is_automated=is_automated,
            triggered_by_user_id=triggered_by_user_id,
            reason=reason,
            status="requested",
            details={"adapter": k8s_adapter.adapter_name},
        )
        db.add(rollback_record)
        deployment.status = "rolling_back"
        db.commit()
        rollback_record.status = "in_progress"
        db.commit()

        # Call adapter rollback
        adapter_result = await k8s_adapter.rollback(
            app_name=project.name,
            namespace=environment.k8s_namespace,
            target_image=restored_release.image_reference or f"{project.image_repository}:{restored_release.image_tag}",
            replicas=environment.replicas
        )

        # Append rollback logs to deployment
        deployment_logs = list(deployment.logs or [])
        deployment_logs.extend(adapter_result.logs)
        deployment_logs.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "WARN",
            "message": f"Rollback executed: Reverted to release {restored_release.version} ({restored_release.image_reference or restored_release.image_tag})"
        })

        rollback_verified = adapter_result.success
        if rollback_verified:
            rollback_verified = await HealthMonitorService.verify_deployment(
                db=db,
                deployment=deployment,
                environment=environment,
                project=project,
                simulate_failure=False,
            )
            deployment_logs.append({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": "INFO" if rollback_verified else "ERROR",
                "message": "Rollback smoke and metrics verification completed.",
            })
        if rollback_verified and not adapter_result.is_simulated:
            pod_status = await k8s_adapter.get_pod_status(
                project.name, environment.k8s_namespace
            )
            rollback_verified = (
                pod_status.get("ready_replicas", 0)
                >= pod_status.get("desired_replicas", environment.replicas)
            )
            deployment_logs.append({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": "INFO" if rollback_verified else "ERROR",
                "message": "Rollback readiness verification completed.",
            })
            discover_endpoint = getattr(k8s_adapter, "discover_service_endpoint", None)
            if rollback_verified and callable(discover_endpoint):
                endpoint = await discover_endpoint(
                    app_name=normalize_kubernetes_name(project.name),
                    namespace=normalize_kubernetes_name(environment.k8s_namespace),
                    port=project.default_port,
                    health_path=project.health_path,
                )
                metadata = dict(deployment.metadata_info or {})
                metadata["endpoint_status"] = endpoint.get("status", "unavailable")
                if endpoint.get("public_url"):
                    metadata["public_url"] = endpoint["public_url"]
                    metadata.pop("endpoint_error", None)
                else:
                    metadata.pop("public_url", None)
                    metadata["endpoint_error"] = endpoint.get(
                        "error", "No reachable endpoint is available after rollback."
                    )
                metadata["endpoint_details"] = {
                    key: value for key, value in endpoint.items() if key != "public_url"
                }
                deployment.metadata_info = metadata
                deployment_logs.append({
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "level": "INFO" if endpoint.get("public_url") else "WARN",
                    "message": (
                        f"Rollback endpoint available at {endpoint['public_url']}"
                        if endpoint.get("public_url")
                        else metadata["endpoint_error"]
                    ),
                })

        deployment.status = "rolled_back" if rollback_verified else "failed"
        deployment.finished_at = datetime.utcnow()
        deployment.logs = deployment_logs
        if not rollback_verified:
            metadata = dict(deployment.metadata_info or {})
            metadata.pop("public_url", None)
            metadata["endpoint_status"] = "error"
            metadata["endpoint_error"] = "Endpoint could not be verified after rollback."
            deployment.metadata_info = metadata

        # Restore environment current_release_id
        if rollback_verified:
            environment.current_release_id = restored_release.id

        rollback_record.status = "successful" if rollback_verified else "failed"
        ROLLBACKS.labels(
            str(is_automated).lower(),
            rollback_record.status,
            str(adapter_result.is_simulated).lower(),
        ).inc()
        rollback_record.details = {
                "adapter": adapter_result.adapter_name,
                "is_simulated": adapter_result.is_simulated,
                "restored_version": restored_release.version,
                "restored_image": restored_release.image_reference or restored_release.image_tag,
                "rollback_verified": rollback_verified,
                "error": None if rollback_verified else adapter_result.message,
            }
        db.commit()
        DEPLOYMENT_DURATION.labels(
            deployment.strategy, deployment.status
        ).observe((deployment.finished_at - deployment.started_at).total_seconds())
        db.refresh(rollback_record)

        # Audit log entry
        AuditService.log_event(
            db=db,
            action="deployment.rollback",
            entity_type="rollback",
            entity_id=rollback_record.id,
            user_id=triggered_by_user_id,
            username=username or ("System Auto-Rollback" if is_automated else None),
            details={
                "deployment_id": deployment.id,
                "failed_release": deployment.release_id,
                "restored_release": restored_release.id,
                "reason": reason,
                "is_automated": is_automated
            }
        )

        return rollback_record
