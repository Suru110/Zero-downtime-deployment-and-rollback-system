"""Rename legacy user fields for public registration authentication."""
from alembic import op
import sqlalchemy as sa

revision = "20261030_0003_public_auth"
down_revision = "20261029_0002_release_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "username",
            new_column_name="name",
            existing_type=sa.String(length=50),
            type_=sa.String(length=100),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "hashed_password",
            new_column_name="password_hash",
            existing_type=sa.String(length=255),
            existing_nullable=False,
        )
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "username",
            type_=sa.String(length=100),
            existing_type=sa.String(length=50),
            existing_nullable=True,
        )
    op.create_index("ix_users_name", "users", ["name"])


def downgrade() -> None:
    op.drop_index("ix_users_name", table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "name",
            new_column_name="username",
            existing_type=sa.String(length=100),
            type_=sa.String(length=50),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "password_hash",
            new_column_name="hashed_password",
            existing_type=sa.String(length=255),
            existing_nullable=False,
        )
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "username",
            type_=sa.String(length=50),
            existing_type=sa.String(length=100),
            existing_nullable=True,
        )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
