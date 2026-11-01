"""initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-29 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # Projects table
    op.create_table(
        'projects',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('git_repo', sa.String(length=255), nullable=False),
        sa.Column('default_branch', sa.String(length=50), nullable=False),
        sa.Column('image_repository', sa.String(length=255), nullable=False),
        sa.Column('default_port', sa.Integer(), nullable=False),
        sa.Column('health_path', sa.String(length=100), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_name'), 'projects', ['name'], unique=True)

    # Releases table
    op.create_table(
        'releases',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('git_commit', sa.String(length=40), nullable=False),
        sa.Column('git_branch', sa.String(length=100), nullable=False),
        sa.Column('image_tag', sa.String(length=100), nullable=False),
        sa.Column('commit_message', sa.Text(), nullable=True),
        sa.Column('changelog', sa.Text(), nullable=True),
        sa.Column('scan_status', sa.String(length=30), nullable=False),
        sa.Column('scan_results', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Environments table
    op.create_table(
        'environments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('k8s_namespace', sa.String(length=100), nullable=False),
        sa.Column('k8s_cluster', sa.String(length=100), nullable=False),
        sa.Column('replicas', sa.Integer(), nullable=False),
        sa.Column('deployment_strategy', sa.String(length=30), nullable=False),
        sa.Column('canary_steps', sa.JSON(), nullable=False),
        sa.Column('auto_rollback_enabled', sa.Boolean(), nullable=False),
        sa.Column('verification_timeout_seconds', sa.Integer(), nullable=False),
        sa.Column('smoke_test_endpoint', sa.String(length=200), nullable=False),
        sa.Column('env_vars', sa.JSON(), nullable=False),
        sa.Column('current_release_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['current_release_id'], ['releases.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Deployments table
    op.create_table(
        'deployments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('environment_id', sa.String(length=36), nullable=False),
        sa.Column('release_id', sa.String(length=36), nullable=False),
        sa.Column('triggered_by', sa.String(length=36), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('strategy', sa.String(length=30), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('is_simulated', sa.Boolean(), nullable=False),
        sa.Column('adapter_name', sa.String(length=50), nullable=False),
        sa.Column('logs', sa.JSON(), nullable=False),
        sa.Column('metadata_info', sa.JSON(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['environment_id'], ['environments.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['release_id'], ['releases.id']),
        sa.ForeignKeyConstraint(['triggered_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Health Checks table
    op.create_table(
        'health_checks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('deployment_id', sa.String(length=36), nullable=False),
        sa.Column('check_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Float(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('executed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['deployment_id'], ['deployments.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Rollback Events table
    op.create_table(
        'rollback_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source_deployment_id', sa.String(length=36), nullable=False),
        sa.Column('environment_id', sa.String(length=36), nullable=False),
        sa.Column('failed_release_id', sa.String(length=36), nullable=False),
        sa.Column('restored_release_id', sa.String(length=36), nullable=False),
        sa.Column('is_automated', sa.Boolean(), nullable=False),
        sa.Column('triggered_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['environment_id'], ['environments.id']),
        sa.ForeignKeyConstraint(['failed_release_id'], ['releases.id']),
        sa.ForeignKeyConstraint(['restored_release_id'], ['releases.id']),
        sa.ForeignKeyConstraint(['source_deployment_id'], ['deployments.id']),
        sa.ForeignKeyConstraint(['triggered_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Audit Logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('username', sa.String(length=50), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.String(length=36), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('rollback_events')
    op.drop_table('health_checks')
    op.drop_table('deployments')
    op.drop_table('environments')
    op.drop_table('releases')
    op.drop_table('projects')
    op.drop_table('users')
