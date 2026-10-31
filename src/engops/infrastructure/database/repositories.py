"""SQLite implementations of the repository interfaces.

They never commit: callers wrap operations in `transaction(conn)`.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime

from engops.domain.common import from_iso, new_id, to_iso, utc_now
from engops.domain.errors import DuplicateRecordError, RecordNotFoundError, RepositoryError
from engops.domain.models import (
    OutputArtifact,
    Process,
    ProcessStatus,
    ProcessVersion,
    Run,
    RunInput,
    RunStatus,
    StoredFile,
)


def _insert(conn: sqlite3.Connection, sql: str, params: tuple) -> None:
    try:
        conn.execute(sql, params)
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc).upper():
            raise DuplicateRecordError(str(exc)) from exc
        raise RepositoryError(str(exc)) from exc


def _opt_iso(value: datetime | None) -> str | None:
    return to_iso(value) if value is not None else None


def _opt_from(text: str | None) -> datetime | None:
    return from_iso(text) if text else None


# --------------------------------------------------------------------------- process


def _to_process(row: sqlite3.Row) -> Process:
    return Process(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        purpose=row["purpose"],
        owner=row["owner"],
        status=ProcessStatus(row["status"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


class SqliteProcessRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, process: Process) -> None:
        _insert(
            self._conn,
            "INSERT INTO process (id, slug, name, purpose, owner, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                process.id,
                process.slug,
                process.name,
                process.purpose,
                process.owner,
                process.status.value,
                to_iso(process.created_at),
                to_iso(process.updated_at),
            ),
        )

    def get(self, process_id: str) -> Process | None:
        row = self._conn.execute("SELECT * FROM process WHERE id = ?", (process_id,)).fetchone()
        return _to_process(row) if row else None

    def get_by_slug(self, slug: str) -> Process | None:
        row = self._conn.execute("SELECT * FROM process WHERE slug = ?", (slug,)).fetchone()
        return _to_process(row) if row else None

    def list_all(self, *, include_retired: bool = False) -> list[Process]:
        sql = "SELECT * FROM process"
        if not include_retired:
            sql += " WHERE status = 'active'"
        sql += " ORDER BY name COLLATE NOCASE, rowid"
        return [_to_process(r) for r in self._conn.execute(sql)]

    def update(self, process: Process) -> Process:
        now = utc_now()
        cursor = self._conn.execute(
            "UPDATE process SET name = ?, purpose = ?, owner = ?, status = ?, updated_at = ? "
            "WHERE id = ?",
            (
                process.name,
                process.purpose,
                process.owner,
                process.status.value,
                to_iso(now),
                process.id,
            ),
        )
        if cursor.rowcount == 0:
            raise RecordNotFoundError(f"Process not found: {process.id}")
        return replace(process, updated_at=now)

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM process").fetchone()[0]


# --------------------------------------------------------------------------- versions


def _to_version(row: sqlite3.Row) -> ProcessVersion:
    return ProcessVersion(
        id=row["id"],
        process_id=row["process_id"],
        version=row["version"],
        manifest=json.loads(row["manifest_json"]),
        approved=bool(row["approved"]),
        approved_by=row["approved_by"],
        approved_at=_opt_from(row["approved_at"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


class SqliteProcessVersionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, version: ProcessVersion) -> None:
        _insert(
            self._conn,
            "INSERT INTO process_version (id, process_id, version, manifest_json, approved, "
            "approved_by, approved_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version.id,
                version.process_id,
                version.version,
                json.dumps(version.manifest, sort_keys=True),
                int(version.approved),
                version.approved_by,
                _opt_iso(version.approved_at),
                to_iso(version.created_at),
                to_iso(version.updated_at),
            ),
        )

    def get(self, version_id: str) -> ProcessVersion | None:
        row = self._conn.execute(
            "SELECT * FROM process_version WHERE id = ?", (version_id,)
        ).fetchone()
        return _to_version(row) if row else None

    def list_for_process(self, process_id: str) -> list[ProcessVersion]:
        rows = self._conn.execute(
            "SELECT * FROM process_version WHERE process_id = ? ORDER BY created_at, rowid",
            (process_id,),
        )
        return [_to_version(r) for r in rows]

    def latest_approved(self, process_id: str) -> ProcessVersion | None:
        row = self._conn.execute(
            "SELECT * FROM process_version WHERE process_id = ? AND approved = 1 "
            "ORDER BY approved_at DESC, rowid DESC LIMIT 1",
            (process_id,),
        ).fetchone()
        return _to_version(row) if row else None

    def approve(self, version_id: str, approved_by: str) -> ProcessVersion:
        existing = self.get(version_id)
        if existing is None:
            raise RecordNotFoundError(f"Process version not found: {version_id}")
        if existing.approved:  # idempotent: the first approval stands
            return existing
        now = utc_now()
        self._conn.execute(
            "UPDATE process_version SET approved = 1, approved_by = ?, approved_at = ?, "
            "updated_at = ? WHERE id = ?",
            (approved_by, to_iso(now), to_iso(now), version_id),
        )
        return replace(
            existing, approved=True, approved_by=approved_by, approved_at=now, updated_at=now
        )


# --------------------------------------------------------------------------- files


class SqliteStoredFileRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, stored: StoredFile) -> None:
        _insert(
            self._conn,
            "INSERT INTO stored_file (id, rel_path, original_name, size_bytes, sha256, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                stored.id,
                stored.rel_path,
                stored.original_name,
                stored.size_bytes,
                stored.sha256,
                to_iso(stored.created_at),
            ),
        )

    def get(self, file_id: str) -> StoredFile | None:
        row = self._conn.execute("SELECT * FROM stored_file WHERE id = ?", (file_id,)).fetchone()
        if row is None:
            return None
        return StoredFile(
            id=row["id"],
            rel_path=row["rel_path"],
            original_name=row["original_name"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            created_at=from_iso(row["created_at"]),
        )


# --------------------------------------------------------------------------- runs


def _to_run(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"],
        process_version_id=row["process_version_id"],
        status=RunStatus(row["status"]),
        started_at=from_iso(row["started_at"]),
        finished_at=_opt_from(row["finished_at"]),
        summary=row["summary"],
        warnings=tuple(json.loads(row["warnings_json"])),
        error=row["error"],
    )


class SqliteRunRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, run: Run) -> None:
        now = to_iso(utc_now())
        _insert(
            self._conn,
            "INSERT INTO run (id, process_version_id, status, started_at, finished_at, summary, "
            "warnings_json, error, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.id,
                run.process_version_id,
                run.status.value,
                to_iso(run.started_at),
                _opt_iso(run.finished_at),
                run.summary,
                json.dumps(list(run.warnings)),
                run.error,
                now,
                now,
            ),
        )

    def get(self, run_id: str) -> Run | None:
        row = self._conn.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
        return _to_run(row) if row else None

    def update(self, run: Run) -> None:
        cursor = self._conn.execute(
            "UPDATE run SET status = ?, finished_at = ?, summary = ?, warnings_json = ?, "
            "error = ?, updated_at = ? WHERE id = ?",
            (
                run.status.value,
                _opt_iso(run.finished_at),
                run.summary,
                json.dumps(list(run.warnings)),
                run.error,
                to_iso(utc_now()),
                run.id,
            ),
        )
        if cursor.rowcount == 0:
            raise RecordNotFoundError(f"Run not found: {run.id}")

    def list_recent(self, *, limit: int = 50, process_id: str | None = None) -> list[Run]:
        sql = "SELECT r.* FROM run r"
        params: list = []
        if process_id is not None:
            sql += " JOIN process_version v ON v.id = r.process_version_id WHERE v.process_id = ?"
            params.append(process_id)
        sql += " ORDER BY r.started_at DESC, r.rowid DESC LIMIT ?"
        params.append(limit)
        return [_to_run(r) for r in self._conn.execute(sql, params)]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM run").fetchone()[0]

    def add_input(self, run_input: RunInput) -> None:
        _insert(
            self._conn,
            "INSERT INTO run_input (id, run_id, role, stored_file_id, original_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_input.id,
                run_input.run_id,
                run_input.role,
                run_input.stored_file_id,
                run_input.original_path,
                to_iso(utc_now()),
            ),
        )

    def list_inputs(self, run_id: str) -> list[RunInput]:
        rows = self._conn.execute(
            "SELECT * FROM run_input WHERE run_id = ? ORDER BY rowid", (run_id,)
        )
        return [
            RunInput(
                id=r["id"],
                run_id=r["run_id"],
                role=r["role"],
                stored_file_id=r["stored_file_id"],
                original_path=r["original_path"],
            )
            for r in rows
        ]

    def add_artifact(self, artifact: OutputArtifact) -> None:
        _insert(
            self._conn,
            "INSERT INTO output_artifact (id, run_id, role, stored_file_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                artifact.id,
                artifact.run_id,
                artifact.role,
                artifact.stored_file_id,
                to_iso(utc_now()),
            ),
        )

    def list_artifacts(self, run_id: str) -> list[OutputArtifact]:
        rows = self._conn.execute(
            "SELECT * FROM output_artifact WHERE run_id = ? ORDER BY rowid", (run_id,)
        )
        return [
            OutputArtifact(
                id=r["id"], run_id=r["run_id"], role=r["role"], stored_file_id=r["stored_file_id"]
            )
            for r in rows
        ]