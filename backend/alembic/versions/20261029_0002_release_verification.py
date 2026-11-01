"""Track immutable release and verification configuration."""
from alembic import op
import sqlalchemy as sa

revision = "20261029_0002_release_verification"
down_revision = "20261029_0001_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("releases", sa.Column("image_digest", sa.String(length=255), nullable=True))
    op.add_column("releases", sa.Column("configuration_revision", sa.String(length=255), nullable=True))
    op.add_column("environments", sa.Column("verification_attempts", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("environments", sa.Column("smoke_test_expected_status", sa.Integer(), nullable=False, server_default="200"))
    op.add_column("environments", sa.Column("smoke_test_timeout_seconds", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("deployments", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_index("ix_deployments_idempotency_key", "deployments", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_deployments_idempotency_key", table_name="deployments")
    op.drop_column("deployments", "idempotency_key")
    op.drop_column("environments", "smoke_test_timeout_seconds")
    op.drop_column("environments", "smoke_test_expected_status")
    op.drop_column("environments", "verification_attempts")
    op.drop_column("releases", "configuration_revision")
    op.drop_column("releases", "image_digest")
