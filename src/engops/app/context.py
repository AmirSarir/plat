"""AppContext: builds and holds the wired-up services for one running app instance."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass

from engops.app.config import Settings
from engops.app.paths import AppPaths
from engops.domain.repositories import (
    ProcessRepository,
    ProcessVersionRepository,
    RunRepository,
    StoredFileRepository,
)
from engops.infrastructure.database.connection import open_connection
from engops.infrastructure.database.migrator import (
    current_version,
    load_packaged_migrations,
    migrate,
)
from engops.infrastructure.database.repositories import (
    SqliteProcessRepository,
    SqliteProcessVersionRepository,
    SqliteRunRepository,
    SqliteStoredFileRepository,
)
from engops.infrastructure.filesystem.file_store import FileStore
from engops.modules.builtin import build_registry
from engops.modules.registry import ModuleRegistry
from engops.services.file_service import FileService
from engops.services.process_catalog import ProcessCatalogService


def ensure_instance_id(conn: sqlite3.Connection) -> str:
    """Stable ID for this installation (future sync: origin_node_id)."""
    row = conn.execute("SELECT value FROM app_meta WHERE key = 'instance_id'").fetchone()
    if row:
        return row["value"]
    instance_id = str(uuid.uuid4())
    conn.execute("INSERT INTO app_meta (key, value) VALUES ('instance_id', ?)", (instance_id,))
    conn.commit()
    return instance_id


@dataclass
class AppContext:
    paths: AppPaths
    settings: Settings
    conn: sqlite3.Connection
    registry: ModuleRegistry
    instance_id: str
    schema_version: int
    processes: ProcessRepository
    versions: ProcessVersionRepository
    stored_files: StoredFileRepository
    runs: RunRepository
    file_store: FileStore
    files: FileService
    catalog: ProcessCatalogService

    def close(self) -> None:
        self.conn.close()


def create_context(paths: AppPaths, settings: Settings) -> AppContext:
    conn = open_connection(paths.db_file)
    try:
        migrate(
            conn,
            load_packaged_migrations(),
            db_file=paths.db_file,
            backup_dir=paths.backups_dir,
        )
        instance_id = ensure_instance_id(conn)

        processes = SqliteProcessRepository(conn)
        versions = SqliteProcessVersionRepository(conn)
        stored_files = SqliteStoredFileRepository(conn)
        runs = SqliteRunRepository(conn)
        file_store = FileStore(paths.files_dir)

        return AppContext(
            paths=paths,
            settings=settings,
            conn=conn,
            registry=build_registry(),
            instance_id=instance_id,
            schema_version=current_version(conn),
            processes=processes,
            versions=versions,
            stored_files=stored_files,
            runs=runs,
            file_store=file_store,
            files=FileService(file_store, stored_files, conn),
            catalog=ProcessCatalogService(conn, processes, versions),
        )
    except BaseException:
        conn.close()
        raise