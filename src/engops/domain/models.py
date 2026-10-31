"""Domain entities. Plain immutable dataclasses: no database or GUI code in here."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ProcessStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return _RUN_LABELS[self]

    @property
    def is_final(self) -> bool:
        return self is not RunStatus.RUNNING


_RUN_LABELS = {
    RunStatus.RUNNING: "Running",
    RunStatus.COMPLETED: "Completed",
    RunStatus.COMPLETED_WITH_WARNINGS: "Completed with warnings",
    RunStatus.PARTIALLY_COMPLETED: "Partially completed",
    RunStatus.FAILED: "Failed",
    RunStatus.CANCELLED: "Cancelled",
}


@dataclass(frozen=True)
class Process:
    id: str
    slug: str  # stable key, also used to find the registered handler
    name: str
    created_at: datetime
    updated_at: datetime
    purpose: str = ""
    owner: str = ""
    status: ProcessStatus = ProcessStatus.ACTIVE


@dataclass(frozen=True)
class ProcessVersion:
    """Immutable once created. A change to the manifest means a new version."""

    id: str
    process_id: str
    version: str
    created_at: datetime
    updated_at: datetime
    manifest: dict[str, Any] = field(default_factory=dict)
    approved: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None


@dataclass(frozen=True)
class StoredFile:
    id: str
    rel_path: str  # relative to the managed files folder, always with '/'
    original_name: str
    size_bytes: int
    sha256: str
    created_at: datetime


@dataclass(frozen=True)
class Run:
    id: str
    process_version_id: str
    started_at: datetime
    status: RunStatus = RunStatus.RUNNING
    finished_at: datetime | None = None
    summary: str = ""
    warnings: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class RunInput:
    id: str
    run_id: str
    role: str  # the input slot name from the process manifest
    stored_file_id: str
    original_path: str = ""  # where the user picked it from (provenance only)


@dataclass(frozen=True)
class OutputArtifact:
    id: str
    run_id: str
    role: str
    stored_file_id: str