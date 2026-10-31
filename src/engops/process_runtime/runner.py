"""ProcessRunner: validates, stages, runs and records one process run."""

from __future__ import annotations

import logging
import sqlite3
import tempfile
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from engops.domain.common import new_id, utc_now
from engops.domain.errors import RecordNotFoundError
from engops.domain.models import OutputArtifact, ProcessStatus, Run, RunInput, RunStatus
from engops.domain.repositories import (
    ProcessRepository,
    ProcessVersionRepository,
    RunRepository,
)
from engops.infrastructure.database.connection import transaction
from engops.process_runtime.contracts import BaseProcessHandler, ProcessContext, RunLog
from engops.process_runtime.errors import ProcessCancelled, ProcessRuntimeError
from engops.process_runtime.manifest import OperationPlan, ProcessManifest
from engops.process_runtime.registry import HandlerRegistry
from engops.process_runtime.validation import Severity, ValidationReport, validate_inputs
from engops.services.file_service import FileService

logger = logging.getLogger(__name__)


class _InputsRejected(Exception):
    pass


@dataclass(frozen=True)
class RunResult:
    run: Run
    artifacts: tuple[OutputArtifact, ...] = ()

    @property
    def ok(self) -> bool:
        return self.run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_WITH_WARNINGS)


def _join(*parts: str | None) -> str | None:
    text = "; ".join(p for p in parts if p)
    return text or None


class ProcessRunner:
    def __init__(
        self,
        conn: sqlite3.Connection,
        processes: ProcessRepository,
        versions: ProcessVersionRepository,
        runs: RunRepository,
        files: FileService,
        handlers: HandlerRegistry,
    ) -> None:
        self._conn = conn
        self._processes = processes
        self._versions = versions
        self._runs = runs
        self._files = files
        self._handlers = handlers

    # ------------------------------------------------------------------ public

    def run(
        self,
        slug: str,
        inputs: Mapping[str, Path],
        *,
        cancel_event: threading.Event | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> RunResult:
        """Run the latest approved version of a process. Blocks until it finishes.

        Raises if the process cannot be run at all (unknown, retired, unapproved, no handler).
        Once a run record exists, problems are recorded on it (status Failed) instead.
        """
        process = self._processes.get_by_slug(slug)
        if process is None:
            raise RecordNotFoundError(f"Unknown process: {slug!r}")
        if process.status is not ProcessStatus.ACTIVE:
            raise ProcessRuntimeError(f"Process {slug!r} is retired.")
        version = self._versions.latest_approved(process.id)
        if version is None:
            raise ProcessRuntimeError(f"Process {slug!r} has no approved version.")
        handler = self._handlers.get(slug)
        manifest = ProcessManifest.from_dict(version.manifest)

        provided = {role: Path(path) for role, path in inputs.items()}
        report = validate_inputs(manifest, provided)
        run = Run(id=new_id(), process_version_id=version.id, started_at=utc_now())

        if report.has_errors:
            return self._reject(run, report)

        with transaction(self._conn):
            self._runs.add(run)
        return self._execute(run, manifest, handler, provided, report, cancel_event, on_log)

    # ----------------------------------------------------------------- internals

    def _reject(self, run: Run, report: ValidationReport) -> RunResult:
        """Validation failed: record a Failed run without starting the process."""
        finished = replace(
            run,
            status=RunStatus.FAILED,
            finished_at=utc_now(),
            summary="Input validation failed; the process was not started.",
            warnings=tuple(i.message for i in report.warnings),
            error="; ".join(i.message for i in report.errors),
        )
        with transaction(self._conn):
            self._runs.add(finished)
        return RunResult(finished)

    def _execute(
        self,
        run: Run,
        manifest: ProcessManifest,
        handler: BaseProcessHandler,
        provided: dict[str, Path],
        report: ValidationReport,
        cancel_event: threading.Event | None,
        on_log: Callable[[str], None] | None,
    ) -> RunResult:
        run_log = RunLog(on_log)
        run_log.info(f"Run {run.id} started")

        status = RunStatus.COMPLETED
        error: str | None = None
        ctx: ProcessContext | None = None
        plan = OperationPlan((), ())
        issue_warnings = [i.message for i in report.warnings]
        artifacts: list[OutputArtifact] = []

        with tempfile.TemporaryDirectory(prefix="engops-run-", ignore_cleanup_errors=True) as tmp:
            work_dir = Path(tmp)
            output_dir = work_dir / "output"
            output_dir.mkdir()

            try:
                staged = self._stage_inputs(run, manifest, provided, run_log)

                extra_issues = handler.validate_inputs(staged)
                issue_warnings += [i.message for i in extra_issues if i.severity is Severity.WARNING]
                rejected = [i.message for i in extra_issues if i.severity is Severity.ERROR]
                if rejected:
                    raise _InputsRejected("; ".join(rejected))

                plan = manifest.plan(staged.keys())
                for skipped in plan.skipped:
                    run_log.skipped(f"{skipped.label}: {skipped.reason}")

                ctx = ProcessContext(
                    run_id=run.id,
                    manifest=manifest,
                    inputs=staged,
                    plan=plan,
                    output_dir=output_dir,
                    run_log=run_log,
                    cancel_event=cancel_event,
                )
                run_log.info("Process started")
                handler.run(ctx)
                run_log.info("Process finished")
            except ProcessCancelled:
                status = RunStatus.CANCELLED
                run_log.warning("The run was cancelled.")
            except _InputsRejected as exc:
                status = RunStatus.FAILED
                error = str(exc)
                run_log.error(f"Input check failed: {error}")
            except Exception as exc:
                logger.exception("Run %s failed", run.id)
                status = RunStatus.FAILED
                error = f"{type(exc).__name__}: {exc}"
                run_log.error(error)

            # Keep whatever outputs were produced, even if the run failed part-way.
            try:
                self._register_outputs(run, ctx, artifacts, run_log)
            except Exception as exc:
                logger.exception("Could not save outputs of run %s", run.id)
                status = RunStatus.FAILED
                error = _join(error, f"Could not save outputs: {exc}")
                run_log.error(f"Could not save outputs: {exc}")

            warnings = list(issue_warnings)
            skipped_all = list(plan.skipped)
            if ctx is not None:
                warnings.extend(ctx.warnings)
                skipped_all.extend(ctx.skipped)
            warnings.extend(f"Skipped '{s.label}': {s.reason}" for s in skipped_all)

            if status is RunStatus.COMPLETED and ctx is not None:
                produced = {role for role, _ in ctx.outputs}
                for spec in manifest.outputs:
                    if spec.required and spec.role not in produced:
                        warnings.append(f"Expected output '{spec.label}' was not produced.")
                if skipped_all:
                    status = RunStatus.PARTIALLY_COMPLETED
                elif warnings:
                    status = RunStatus.COMPLETED_WITH_WARNINGS

            summary = self._summary(status, manifest, plan, ctx, len(artifacts))
            run_log.info(f"Run finished: {status.label}. {summary}")
            self._register_log(run, run_log, work_dir, artifacts)

        finished = replace(
            run,
            status=status,
            finished_at=utc_now(),
            summary=summary,
            warnings=tuple(warnings),
            error=error,
        )
        with transaction(self._conn):
            self._runs.update(finished)
        return RunResult(finished, tuple(artifacts))

    def _stage_inputs(
        self,
        run: Run,
        manifest: ProcessManifest,
        provided: dict[str, Path],
        run_log: RunLog,
    ) -> dict[str, Path]:
        """Copy each input into the managed store; handlers only ever see these copies."""
        staged: dict[str, Path] = {}
        for spec in manifest.inputs:
            source = provided.get(spec.role)
            if source is None:
                continue
            stored = self._files.import_file(source, "inputs")
            with transaction(self._conn):
                self._runs.add_input(
                    RunInput(
                        id=new_id(),
                        run_id=run.id,
                        role=spec.role,
                        stored_file_id=stored.id,
                        original_path=str(source),
                    )
                )
            staged[spec.role] = self._files.path_of(stored)
            run_log.info(
                f"Staged input '{spec.label}': {source.name} "
                f"({stored.size_bytes} bytes, sha256 {stored.sha256[:12]}...)"
            )
        return staged

    def _register_outputs(
        self,
        run: Run,
        ctx: ProcessContext | None,
        artifacts: list[OutputArtifact],
        run_log: RunLog,
    ) -> None:
        if ctx is None:
            return
        for role, path in ctx.outputs:
            stored = self._files.import_file(path, "outputs")
            artifact = OutputArtifact(
                id=new_id(), run_id=run.id, role=role, stored_file_id=stored.id
            )
            with transaction(self._conn):
                self._runs.add_artifact(artifact)
            artifacts.append(artifact)
            run_log.info(f"Saved output '{role}': {path.name} ({stored.size_bytes} bytes)")

    def _register_log(
        self, run: Run, run_log: RunLog, work_dir: Path, artifacts: list[OutputArtifact]
    ) -> None:
        """Best effort: a problem saving the log must not hide the run's real result."""
        try:
            log_path = work_dir / "run_log.txt"
            log_path.write_text(run_log.text(), encoding="utf-8")
            stored = self._files.import_file(log_path, "outputs")
            artifact = OutputArtifact(
                id=new_id(), run_id=run.id, role="run_log", stored_file_id=stored.id
            )
            with transaction(self._conn):
                self._runs.add_artifact(artifact)
            artifacts.append(artifact)
        except Exception:
            logger.exception("Could not save the run log for run %s", run.id)

    @staticmethod
    def _summary(
        status: RunStatus,
        manifest: ProcessManifest,
        plan: OperationPlan,
        ctx: ProcessContext | None,
        output_count: int,
    ) -> str:
        if status is RunStatus.FAILED:
            return "The process failed. See the error and the run log."
        if status is RunStatus.CANCELLED:
            return "The run was cancelled before it finished."
        parts: list[str] = []
        if manifest.operations and ctx is not None:
            ran = sum(1 for op in plan.enabled if ctx.operation_enabled(op.id))
            parts.append(f"{ran} of {len(manifest.operations)} operations ran")
        parts.append(f"{output_count} output file(s) produced")
        return "; ".join(parts) + "."