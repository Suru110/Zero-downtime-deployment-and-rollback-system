from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.config import BACKEND_ROOT, settings
from app.core.database import engine
from app.core.logging import get_logger

logger = get_logger("releasepilot.migrations")


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return config


def _has_revision() -> bool:
    inspector = inspect(engine)
    if "alembic_version" not in inspector.get_table_names():
        return False
    with engine.connect() as connection:
        return connection.execute(text("SELECT 1 FROM alembic_version LIMIT 1")).first() is not None


def _legacy_baseline() -> str | None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return None

    indexes = {
        index["name"]
        for table in ("environments", "releases", "deployments", "health_checks", "audit_logs")
        if table in tables
        for index in inspector.get_indexes(table)
    }
    if "ix_environments_project_name" in indexes:
        return "20261029_0001_indexes"
    return "001_initial_schema"


def run_migrations() -> None:
    """Upgrade the configured database, preserving unversioned legacy data."""
    logger.info("Checking database migration state.")
    baseline = None
    if not _has_revision():
        baseline = _legacy_baseline()
        if baseline:
            logger.warning(
                "Existing unversioned database detected; stamping verified baseline %s before upgrade.",
                baseline,
            )
            command.stamp(_alembic_config(), baseline)

    logger.info("Applying database migrations to head.")
    command.upgrade(_alembic_config(), "head")
    logger.info("Database migrations completed successfully.")
    if baseline:
        logger.info("Legacy database migrated from %s to head.", baseline)
