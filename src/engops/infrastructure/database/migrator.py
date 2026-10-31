"""Tiny forward-only SQL migration runner.

Migrations are files named NNNN_description.sql inside the `migrations` package.
Each one runs in a single transaction together with its bookkeeping row, so a
failed migration leaves the database exactly as it was.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from engops.infrastructure.database.connection import backup_database

log = logging.getLogger(__name__)

_FILE_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


class MigrationError(RuntimeError):
    pass


def load_packaged_migrations() -> list[Migration]:
    package = resources.files("engops.infrastructure.database.migrations")
    found: list[Migration] = []
    for entry in package.iterdir():
        match = _FILE_RE.match(entry.name)
        if match:
            found.append(
                Migration(int(match.group(1)), match.group(2), entry.read_text(encoding="utf-8"))
            )
    found.sort(key=lambda m: m.version)
    versions = [m.version for m in found]
    if len(versions) != len(set(versions)):
        raise MigrationError("Duplicate migration version numbers found")
    return found


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    _ensure_table(conn)
    return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}


def current_version(conn: sqlite3.Connection) -> int:
    versions = applied_versions(conn)
    return max(versions) if versions else 0


def migrate(
    conn: sqlite3.Connection,
    migrations: list[Migration],
    *,
    db_file: Path | None = None,
    backup_dir: Path | None = None,
) -> list[int]:
    """Apply pending migrations. Returns the versions applied."""
    applied = applied_versions(conn)
    known = {m.version for m in migrations}

    unknown = applied - known
    if unknown:
        raise MigrationError(
            f"Database has migrations this app does not know about: {sorted(unknown)}. "
            "It was probably created by a newer version of the app."
        )

    todo = sorted((m for m in migrations if m.version not in applied), key=lambda m: m.version)
    if not todo:
        return []

    # Safety copy before changing an existing (non-empty) database.
    if applied and backup_dir is not None and db_file is not None and db_file.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = backup_dir / f"pre-migration-v{max(applied):04d}-{stamp}.sqlite3"
        backup_database(conn, dest)
        log.info("Database backed up to %s before migrating", dest)

    done: list[int] = []
    for migration in todo:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        safe_name = migration.name.replace("'", "''")
        script = (
            "BEGIN;\n"
            f"{migration.sql}\n;\n"
            "INSERT INTO schema_migrations (version, name, applied_at) "
            f"VALUES ({int(migration.version)}, '{safe_name}', '{stamp}');\n"
            "COMMIT;"
        )
        try:
            conn.executescript(script)
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.rollback()
            raise MigrationError(
                f"Migration {migration.version:04d}_{migration.name} failed: {exc}"
            ) from exc
        log.info("Applied migration %04d_%s", migration.version, migration.name)
        done.append(migration.version)
    return done