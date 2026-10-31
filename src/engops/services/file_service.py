"""Imports files into the managed store and records them in the database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from engops.domain.common import utc_now
from engops.domain.models import StoredFile
from engops.domain.repositories import StoredFileRepository
from engops.infrastructure.database.connection import transaction
from engops.infrastructure.filesystem.file_store import FileStore


class FileService:
    def __init__(
        self, store: FileStore, repo: StoredFileRepository, conn: sqlite3.Connection
    ) -> None:
        self._store = store
        self._repo = repo
        self._conn = conn

    def import_file(self, source: Path, category: str) -> StoredFile:
        """Copy a file into the store and register it. Cleans up the copy if registering fails."""
        info = self._store.add_file(source, category)
        stored = StoredFile(
            id=info.file_id,
            rel_path=info.rel_path,
            original_name=info.original_name,
            size_bytes=info.size_bytes,
            sha256=info.sha256,
            created_at=utc_now(),
        )
        try:
            with transaction(self._conn):
                self._repo.add(stored)
        except BaseException:
            self._store.discard(info.rel_path)
            raise
        return stored

    def path_of(self, stored: StoredFile) -> Path:
        return self._store.path_of(stored.rel_path)

    def verify(self, stored: StoredFile) -> bool:
        return self._store.verify(stored.rel_path, stored.sha256, stored.size_bytes)