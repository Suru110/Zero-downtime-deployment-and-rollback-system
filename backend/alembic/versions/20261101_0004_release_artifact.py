"""Persist the exact image reference and release publication status."""
from alembic import op
import sqlalchemy as sa

revision = "20261101_0004_release_artifact"
down_revision = "20261030_0003_public_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("releases", sa.Column("image_reference", sa.String(length=255), nullable=True))
    op.add_column(
        "releases",
        sa.Column("build_status", sa.String(length=30), nullable=False, server_default="published"),
    )
    op.execute(
        """
        UPDATE releases
        SET image_reference = (
            SELECT projects.image_repository || ':' || releases.image_tag
            FROM projects
            WHERE projects.id = releases.project_id
        )
        WHERE image_reference IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("releases", "build_status")
    op.drop_column("releases", "image_reference")
