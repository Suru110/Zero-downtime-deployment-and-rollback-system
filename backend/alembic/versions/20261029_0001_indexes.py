"""Add indexes used by the deployment and audit query paths."""
from alembic import op

revision = "20261029_0001_indexes"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_environments_project_name",
        "environments",
        ["project_id", "name"],
        unique=True,
    )
    op.create_index(
        "ix_releases_project_version",
        "releases",
        ["project_id", "version"],
        unique=True,
    )
    op.create_index(
        "ix_releases_project_created",
        "releases",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_deployments_environment_started",
        "deployments",
        ["environment_id", "started_at"],
    )
    op.create_index("ix_deployments_status", "deployments", ["status"])
    op.create_index(
        "ix_health_checks_deployment_executed",
        "health_checks",
        ["deployment_id", "executed_at"],
    )
    op.create_index(
        "ix_audit_logs_entity_created",
        "audit_logs",
        ["entity_type", "entity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_entity_created", table_name="audit_logs")
    op.drop_index("ix_health_checks_deployment_executed", table_name="health_checks")
    op.drop_index("ix_deployments_status", table_name="deployments")
    op.drop_index("ix_deployments_environment_started", table_name="deployments")
    op.drop_index("ix_releases_project_created", table_name="releases")
    op.drop_index("ix_releases_project_version", table_name="releases")
    op.drop_index("ix_environments_project_name", table_name="environments")
