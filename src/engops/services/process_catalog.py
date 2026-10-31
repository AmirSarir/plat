"""Registering processes and their versions, and approving versions."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from engops.domain.common import new_id, utc_now
from engops.domain.errors import RecordNotFoundError, ValidationError
from engops.domain.models import Process, ProcessVersion
from engops.domain.repositories import ProcessRepository, ProcessVersionRepository
from engops.infrastructure.database.connection import transaction

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,59}$")


class ProcessCatalogService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        processes: ProcessRepository,
        versions: ProcessVersionRepository,
    ) -> None:
        self._conn = conn
        self._processes = processes
        self._versions = versions

    def register_process(
        self, *, slug: str, name: str, purpose: str = "", owner: str = ""
    ) -> Process:
        slug, name = slug.strip(), name.strip()
        if not _SLUG_RE.match(slug):
            raise ValidationError(
                "Slug must be 2-60 characters: lowercase letters, digits and underscores, "
                "starting with a letter."
            )
        if not name:
            raise ValidationError("Process name is required.")
        now = utc_now()
        process = Process(
            id=new_id(),
            slug=slug,
            name=name,
            purpose=purpose.strip(),
            owner=owner.strip(),
            created_at=now,
            updated_at=now,
        )
        with transaction(self._conn):
            self._processes.add(process)
        return process

    def add_version(
        self, process_id: str, version: str, manifest: dict[str, Any] | None = None
    ) -> ProcessVersion:
        version = version.strip()
        if not version:
            raise ValidationError("Version is required.")
        if self._processes.get(process_id) is None:
            raise RecordNotFoundError(f"Process not found: {process_id}")
        now = utc_now()
        item = ProcessVersion(
            id=new_id(),
            process_id=process_id,
            version=version,
            manifest=manifest or {},
            created_at=now,
            updated_at=now,
        )
        with transaction(self._conn):
            self._versions.add(item)
        return item

    def approve_version(self, version_id: str, approved_by: str) -> ProcessVersion:
        approved_by = approved_by.strip()
        if not approved_by:
            raise ValidationError("Who approved this version is required.")
        with transaction(self._conn):
            return self._versions.approve(version_id, approved_by)