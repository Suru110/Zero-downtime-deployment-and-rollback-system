from datetime import datetime, timedelta
from app.core.database import SessionLocal, init_db
from app.models.project import Project
from app.models.environment import Environment
from app.models.release import Release
from app.models.deployment import Deployment
from app.models.health_check import HealthCheck
from app.core.logging import get_logger

logger = get_logger("releasepilot.seed")

def seed_database():
    logger.info("Initializing database schema...")
    init_db()

    db = SessionLocal()
    try:
        # Seed sample applications only. User accounts are created through public registration.
        apps_data = [
            {
                "name": "payment-gateway",
                "description": "PCI-compliant payment transaction routing and authorization engine.",
                "git_repo": "https://github.com/releasepilot-demo/payment-gateway.git",
                "default_branch": "main",
                "image_repository": "docker.io/releasepilot/payment-gateway",
                "default_port": 8080,
                "health_path": "/healthz",
                "envs": [
                    {"name": "staging", "namespace": "payments-staging", "replicas": 2, "strategy": "rolling"},
                    {"name": "production", "namespace": "payments-prod", "replicas": 4, "strategy": "canary"}
                ],
                "releases": [
                    {"version": "v1.0.0", "commit": "3a9c7b12d5f8", "tag": "v1.0.0", "status": "clean"},
                    {"version": "v1.1.0", "commit": "7e4f8a29c1b3", "tag": "v1.1.0", "status": "clean"},
                    {"version": "v1.2.0-rc1", "commit": "b5c1d93e84f2", "tag": "v1.2.0-rc1", "status": "clean"}
                ]
            },
            {
                "name": "checkout-service",
                "description": "Customer shopping cart, discount calculation, and checkout pipeline.",
                "git_repo": "https://github.com/releasepilot-demo/checkout-service.git",
                "default_branch": "main",
                "image_repository": "docker.io/releasepilot/checkout-service",
                "default_port": 3000,
                "health_path": "/api/v1/health",
                "envs": [
                    {"name": "dev", "namespace": "checkout-dev", "replicas": 1, "strategy": "rolling"},
                    {"name": "production", "namespace": "checkout-prod", "replicas": 3, "strategy": "rolling"}
                ],
                "releases": [
                    {"version": "v2.3.0", "commit": "c4d7e10a29b8", "tag": "v2.3.0", "status": "clean"},
                    {"version": "v2.4.0", "commit": "e8a1f73b95d2", "tag": "v2.4.0", "status": "clean"}
                ]
            },
            {
                "name": "order-fulfillment",
                "description": "Asynchronous warehouse dispatch, courier dispatching, and tracking updates.",
                "git_repo": "https://github.com/releasepilot-demo/order-fulfillment.git",
                "default_branch": "main",
                "image_repository": "docker.io/releasepilot/order-fulfillment",
                "default_port": 5000,
                "health_path": "/health",
                "envs": [
                    {"name": "production", "namespace": "fulfillment-prod", "replicas": 2, "strategy": "rolling"}
                ],
                "releases": [
                    {"version": "v0.9.5", "commit": "f1d4a8e2c7b9", "tag": "v0.9.5", "status": "clean"}
                ]
            }
        ]

        for app_spec in apps_data:
            project = db.query(Project).filter(Project.name == app_spec["name"]).first()
            if not project:
                logger.info(f"Seeding project '{app_spec['name']}'...")
                project = Project(
                    name=app_spec["name"],
                    description=app_spec["description"],
                    git_repo=app_spec["git_repo"],
                    default_branch=app_spec["default_branch"],
                    image_repository=app_spec["image_repository"],
                    default_port=app_spec["default_port"],
                    health_path=app_spec["health_path"],
                    owner_id=None
                )
                db.add(project)
                db.commit()
                db.refresh(project)

                # Seed Releases
                created_releases = []
                for rel in app_spec["releases"]:
                    r = Release(
                        project_id=project.id,
                        version=rel["version"],
                        git_commit=rel["commit"],
                        image_tag=rel["tag"],
                        commit_message=f"Release {rel['version']} updates and performance enhancements",
                        scan_status=rel["status"],
                        scan_results={
                            "is_simulated": True,
                            "status": rel["status"],
                            "critical_count": 0,
                            "high_count": 0,
                            "medium_count": 1,
                            "low_count": 2
                        }
                    )
                    db.add(r)
                    created_releases.append(r)
                db.commit()

                # Seed Environments
                for env_spec in app_spec["envs"]:
                    env = Environment(
                        project_id=project.id,
                        name=env_spec["name"],
                        k8s_namespace=env_spec["namespace"],
                        replicas=env_spec["replicas"],
                        deployment_strategy=env_spec["strategy"],
                        current_release_id=created_releases[0].id if created_releases else None,
                        auto_rollback_enabled=True,
                        verification_timeout_seconds=60,
                        smoke_test_endpoint=project.health_path,
                        env_vars={"APP_ENV": env_spec["name"], "LOG_LEVEL": "info"}
                    )
                    db.add(env)
                    db.commit()
                    db.refresh(env)

                    # Seed initial successful deployment for each environment
                    dep = Deployment(
                        project_id=project.id,
                        environment_id=env.id,
                        release_id=created_releases[0].id,
                        triggered_by=None,
                        status="active",
                        strategy=env_spec["strategy"],
                        progress=100,
                        is_simulated=True,
                        adapter_name="k8s-rolling" if env_spec["strategy"] == "rolling" else "k8s-canary",
                        logs=[
                            {"timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z", "level": "INFO", "message": f"Deployment initialized for {project.name}"},
                            {"timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z", "level": "INFO", "message": "Applying Kubernetes deployment manifest..."},
                            {"timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z", "level": "INFO", "message": "Synthetic readiness probe passed (HTTP 200 OK)"},
                            {"timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z", "level": "INFO", "message": f"Release {created_releases[0].version} marked active."}
                        ],
                        metadata_info={"seeded": True},
                        started_at=datetime.utcnow() - timedelta(hours=2),
                        finished_at=datetime.utcnow() - timedelta(hours=2, seconds=-45)
                    )
                    db.add(dep)
                    db.commit()
                    db.refresh(dep)

                    # Seed Health Check
                    hc = HealthCheck(
                        deployment_id=dep.id,
                        check_type="readiness_probe",
                        status="passed",
                        status_code=200,
                        latency_ms=14.2,
                        details={"status": "2/2 pods ready"}
                    )
                    db.add(hc)

        logger.info("Seed data successfully populated.")
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
