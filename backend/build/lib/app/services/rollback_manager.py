from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.deployment import Deployment
from app.models.environment import Environment
from app.models.release import Release
from app.models.rollback import RollbackEvent
from app.adapters import get_deployment_adapter
from app.services.audit_service import AuditService
from app.core.logging import get_logger

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
            # Fallback to the latest available release that is not the failed one
            restored_release = (
                db.query(Release)
                .filter(Release.project_id == deployment.project_id, Release.id != deployment.release_id)
                .order_by(Release.created_at.desc())
                .first()
            )

        if not restored_release:
            raise ValueError("No previous release available for rollback")

        project = environment.project
        k8s_adapter = get_deployment_adapter()

        logger.warning(
            f"INITIATING ROLLBACK: Dep={deployment.id} TargetRelease={restored_release.version} Reason='{reason}'"
        )

        # Call adapter rollback
        adapter_result = await k8s_adapter.rollback(
            app_name=project.name,
            namespace=environment.k8s_namespace,
            target_image=f"{project.image_repository}:{restored_release.image_tag}",
            replicas=environment.replicas
        )

        # Append rollback logs to deployment
        deployment_logs = list(deployment.logs or [])
        deployment_logs.extend(adapter_result.logs)
        deployment_logs.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "WARN",
            "message": f"Rollback executed: Reverted to release {restored_release.version} ({restored_release.image_tag})"
        })

        deployment.status = "rolled_back"
        deployment.finished_at = datetime.utcnow()
        deployment.logs = deployment_logs

        # Restore environment current_release_id
        environment.current_release_id = restored_release.id

        rollback_record = RollbackEvent(
            source_deployment_id=deployment.id,
            environment_id=environment.id,
            failed_release_id=deployment.release_id,
            restored_release_id=restored_release.id,
            is_automated=is_automated,
            triggered_by_user_id=triggered_by_user_id,
            reason=reason,
            status="completed" if adapter_result.success else "failed",
            details={
                "adapter": adapter_result.adapter_name,
                "is_simulated": adapter_result.is_simulated,
                "restored_version": restored_release.version,
                "restored_image": restored_release.image_tag
            }
        )

        db.add(rollback_record)
        db.commit()
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
