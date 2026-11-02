"""Back up the configured database and remove all user accounts safely.

This script intentionally requires --confirm-reset. It preserves applications,
releases, deployments, health checks, rollback events, and audit logs while
nulling their references to deleted users.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.database import engine


def _sqlite_path() -> Path:
    if not settings.DATABASE_URL.startswith("sqlite:///"):
        raise RuntimeError("This controlled reset script only supports SQLite databases.")
    return Path(settings.DATABASE_URL.removeprefix("sqlite:///")).resolve()


def reset_users(backup_path: Path) -> dict[str, int]:
    database_path = _sqlite_path()
    if not database_path.exists():
        raise FileNotFoundError(f"Configured database does not exist: {database_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database_path, backup_path)

    deleted: dict[str, int] = {}
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        # Delete only session/token-style records. Domain records are retained.
        for table in sorted(tables):
            if table in {"users", "alembic_version"}:
                continue
            columns = {column["name"] for column in inspector.get_columns(table)}
            if "user_id" in columns and any(
                marker in table.lower()
                for marker in ("session", "token", "refresh", "auth")
            ):
                result = connection.execute(text(f'DELETE FROM "{table}" WHERE user_id IS NOT NULL'))
                deleted[table] = result.rowcount

        # Preserve domain history and remove only references to deleted users.
        for table, column in (
            ("projects", "owner_id"),
            ("deployments", "triggered_by"),
            ("rollback_events", "triggered_by_user_id"),
            ("audit_logs", "user_id"),
        ):
            if table in tables and column in {
                column["name"] for column in inspector.get_columns(table)
            }:
                connection.execute(text(f'UPDATE "{table}" SET "{column}" = NULL WHERE "{column}" IS NOT NULL'))

        result = connection.execute(text('DELETE FROM "users"'))
        deleted["users"] = result.rowcount

    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-reset", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    database_path = _sqlite_path()
    backup_path = args.backup or (
        database_path.parent
        / "backups"
        / f"releasepilot-before-user-reset-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.db"
    )

    print(f"Configured database: {database_path}")
    print(f"Backup destination: {backup_path.resolve()}")
    if not args.confirm_reset:
        raise SystemExit("Refusing to delete users. Re-run with --confirm-reset after reviewing the paths.")

    deleted = reset_users(backup_path.resolve())
    print(f"Backup created: {backup_path.resolve()}")
    print(f"Deleted records: {deleted}")
    print("Preserved: projects, environments, releases, deployments, health checks, rollback events, and audit logs.")


if __name__ == "__main__":
    main()
