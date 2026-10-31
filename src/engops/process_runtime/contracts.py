"""What a process handler sees (ProcessContext) and must implement (BaseProcessHandler)."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import ClassVar

from engops.domain.common import to_iso, utc_now
from engops.infrastructure.filesystem.file_store import sanitize_filename
from engops.process_runtime.errors import ProcessCancelled, ProcessInputError, ProcessRuntimeError
from engops.process_runtime.manifest import OperationPlan, ProcessManifest, SkippedOperation
from engops.process_runtime.validation import ValidationIssue

log = logging.getLogger(__name__)


class RunLog:
    """Timestamped log lines with readable severity labels (not just colors)."""

    def __init__(self, on_line: Callable[[str], None] | None = None) -> None:
        self._lines: list[str] = []
        self._on_line = on_line

    def add(self, level: str, message: str) -> None:
        line = f"{to_iso(utc_now())} [{level}] {message}"
        self._lines.append(line)
        if self._on_line is not None:
            try:
                self._on_line(line)
            except Exception:  # a broken UI callback must never break a run
                log.exception("Run log callback failed")

    def info(self, message: str) -> None:
        self.add("INFO", message)

    def warning(self, message: str) -> None:
        self.add("WARNING", message)

    def skipped(self, message: str) -> None:
        self.add("SKIPPED", message)

    def error(self, message: str) -> None:
        self.add("ERROR", message)

    @property
    def lines(self) -> tuple[str, ...]:
        return tuple(self._lines)

    def text(self) -> str:
        return "\n".join(self._lines) + "\n"


class ProcessContext:
    """Everything a handler is allowed to touch during one run."""

    def __init__(
        self,
        *,
        run_id: str,
        manifest: ProcessManifest,
        inputs: Mapping[str, Path],
        plan: OperationPlan,
        output_dir: Path,
        run_log: RunLog,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self._run_id = run_id
        self._manifest = manifest
        self._inputs = dict(inputs)
        self._plan = plan
        self._output_dir = Path(output_dir)
        self._log = run_log
        self._cancel_event = cancel_event
        self._warnings: list[str] = []
        self._skipped: list[SkippedOperation] = []
        self._outputs: list[tuple[str, Path]] = []
        self._reserved: set[Path] = set()

    # ------------------------------------------------------------------ inputs

    @property
    def run_id(self) -> str:
        return self._run_id

    def has_input(self, role: str) -> bool:
        return role in self._inputs

    def input_path(self, role: str) -> Path:
        """Path of a staged input copy. Treat it as read-only."""
        try:
            return self._inputs[role]
        except KeyError:
            raise ProcessInputError(f"Input '{role}' was not provided.") from None

    # -------------------------------------------------------------- operations

    def operation_enabled(self, operation_id: str) -> bool:
        """True if the operation's required inputs are present and it was not skipped."""
        if any(s.operation_id == operation_id for s in self._skipped):
            return False
        return self._plan.is_enabled(operation_id)

    def skip(self, operation: str, reason: str) -> None:
        """Skip an operation at run time (e.g. because the data turned out unusable)."""
        label = next((o.label for o in self._manifest.operations if o.id == operation), operation)
        self._skipped.append(SkippedOperation(operation, label, reason))
        self._log.skipped(f"{label}: {reason}")

    # ----------------------------------------------------------------- logging

    def log(self, message: str) -> None:
        self._log.info(message)

    def warn(self, message: str) -> None:
        self._warnings.append(message)
        self._log.warning(message)

    def check_cancelled(self) -> None:
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise ProcessCancelled()

    # ----------------------------------------------------------------- outputs

    def new_output_path(self, filename: str) -> Path:
        """A fresh, non-colliding path inside this run's output folder."""
        name = sanitize_filename(filename)
        stem, suffix = Path(name).stem, Path(name).suffix
        candidate = self._output_dir / name
        counter = 2
        while candidate.exists() or candidate in self._reserved:
            candidate = self._output_dir / f"{stem} ({counter}){suffix}"
            counter += 1
        self._reserved.add(candidate)
        return candidate

    def add_output(self, role: str, path: Path) -> None:
        """Declare a finished output file. The role must exist in the manifest."""
        if self._manifest.output_spec(role) is None:
            raise ProcessRuntimeError(f"Output role '{role}' is not declared in the manifest.")
        resolved = Path(path).resolve()
        if self._output_dir.resolve() not in resolved.parents:
            raise ProcessRuntimeError(
                "Outputs must be created inside the run's output folder (use new_output_path)."
            )
        if not resolved.is_file():
            raise ProcessRuntimeError(f"Output file does not exist: {resolved.name}")
        self._outputs.append((role, resolved))

    # ----------------------------------------------- read by the runner afterwards

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    @property
    def skipped(self) -> tuple[SkippedOperation, ...]:
        return tuple(self._skipped)

    @property
    def outputs(self) -> tuple[tuple[str, Path], ...]:
        return tuple(self._outputs)


class BaseProcessHandler(ABC):
    """Base class for every runnable process. Subclasses set `slug` and implement `run`."""

    slug: ClassVar[str]

    def validate_inputs(self, inputs: Mapping[str, Path]) -> list[ValidationIssue]:
        """Optional deeper checks (sheets, columns...) on the staged copies."""
        return []

    @abstractmethod
    def run(self, ctx: ProcessContext) -> None:
        """Do the work. Raise on failure; use ctx.warn/skip for non-fatal problems."""