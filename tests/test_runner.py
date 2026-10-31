import threading
from types import SimpleNamespace

import pytest

from engops.domain.errors import RecordNotFoundError
from engops.domain.models import RunStatus
from engops.infrastructure.filesystem.file_store import FileStore
from engops.process_runtime.contracts import BaseProcessHandler
from engops.process_runtime.demo import DEMO_MANIFEST, DEMO_SLUG, DemoEchoHandler
from engops.process_runtime.errors import ProcessRuntimeError
from engops.process_runtime.registry import HandlerRegistry
from engops.process_runtime.runner import ProcessRunner
from engops.process_runtime.validation import Severity, ValidationIssue
from engops.services.file_service import FileService
from engops.services.process_catalog import ProcessCatalogService


class BoomHandler(BaseProcessHandler):
    slug = "boom_proc"

    def run(self, ctx):
        path = ctx.new_output_path("partial.txt")
        path.write_text("partial", encoding="utf-8")
        ctx.add_output("out", path)
        raise RuntimeError("kaboom")


class RejectHandler(BaseProcessHandler):
    slug = "reject_proc"

    def validate_inputs(self, inputs):
        return [ValidationIssue(Severity.ERROR, "Sheet 'Data' is missing.", "source")]

    def run(self, ctx):
        raise AssertionError("must not run")


@pytest.fixture
def runtime(tmp_path, conn, repos):
    files = FileService(FileStore(tmp_path / "store"), repos.files, conn)
    handlers = HandlerRegistry()
    for handler in (DemoEchoHandler(), BoomHandler(), RejectHandler()):
        handlers.register(handler)
    return SimpleNamespace(
        runner=ProcessRunner(conn, repos.processes, repos.versions, repos.runs, files, handlers),
        catalog=ProcessCatalogService(conn, repos.processes, repos.versions),
        repos=repos,
        files=files,
    )


def _publish(runtime, slug, manifest, *, approve=True):
    process = runtime.catalog.register_process(slug=slug, name=slug)
    version = runtime.catalog.add_version(process.id, "1.0.0", manifest)
    if approve:
        runtime.catalog.approve_version(version.id, "tester")
    return process


def _text(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(data, encoding="utf-8")
    return path


def _artifact_text(runtime, result, role):
    artifact = next(a for a in result.artifacts if a.role == role)
    stored = runtime.repos.files.get(artifact.stored_file_id)
    return runtime.files.path_of(stored).read_text(encoding="utf-8")


def test_full_run_completes_records_everything_and_keeps_originals(runtime, tmp_path):
    _publish(runtime, DEMO_SLUG, DEMO_MANIFEST)
    a = _text(tmp_path, "a.txt", "hello world\nsecond line\n")
    b = _text(tmp_path, "b.txt", "hello world\nanother line\nthird\n")
    before = (a.read_bytes(), b.read_bytes())
    lines = []

    result = runtime.runner.run(DEMO_SLUG, {"source": a, "extra": b}, on_log=lines.append)

    run = result.run
    assert run.status is RunStatus.COMPLETED
    assert run.finished_at is not None and run.error is None
    assert sorted(x.role for x in result.artifacts) == ["comparison", "run_log", "summary"]
    assert runtime.repos.runs.get(run.id) == run
    assert lines  # live log callback received lines

    inputs = runtime.repos.runs.list_inputs(run.id)
    assert {i.role: i.original_path for i in inputs} == {"source": str(a), "extra": str(b)}
    staged = runtime.repos.files.get(inputs[0].stored_file_id)
    assert runtime.files.path_of(staged) != a  # handlers work on staged copies

    assert (a.read_bytes(), b.read_bytes()) == before  # originals untouched
    assert "Lines: 2" in _artifact_text(runtime, result, "summary")


def test_missing_optional_input_gives_partial_result(runtime, tmp_path):
    _publish(runtime, DEMO_SLUG, DEMO_MANIFEST)
    a = _text(tmp_path, "a.txt", "one\ntwo\n")

    result = runtime.runner.run(DEMO_SLUG, {"source": a})

    run = result.run
    assert run.status is RunStatus.PARTIALLY_COMPLETED
    assert any("Skipped" in w and "Second text file" in w for w in run.warnings)
    assert sorted(x.role for x in result.artifacts) == ["run_log", "summary"]
    assert "1 of 2 operations" in run.summary


def test_missing_required_input_fails_without_running(runtime, tmp_path):
    _publish(runtime, DEMO_SLUG, DEMO_MANIFEST)
    b = _text(tmp_path, "b.txt", "x")

    result = runtime.runner.run(DEMO_SLUG, {"extra": b})

    assert result.run.status is RunStatus.FAILED
    assert "Source text file" in result.run.error
    assert result.artifacts == ()
    assert runtime.repos.runs.list_inputs(result.run.id) == []
    assert runtime.repos.runs.get(result.run.id) == result.run  # still recorded


def test_handler_exception_fails_but_keeps_partial_outputs_and_log(runtime, tmp_path):
    _publish(runtime, "boom_proc", {"outputs": [{"role": "out", "label": "Out"}]})

    result = runtime.runner.run("boom_proc", {})

    assert result.run.status is RunStatus.FAILED
    assert "kaboom" in result.run.error
    assert sorted(x.role for x in result.artifacts) == ["out", "run_log"]


def test_handler_warning_gives_completed_with_warnings(runtime, tmp_path):
    _publish(runtime, DEMO_SLUG, DEMO_MANIFEST)
    blank = _text(tmp_path, "blank.txt", "  \n")
    b = _text(tmp_path, "b.txt", "x")

    result = runtime.runner.run(DEMO_SLUG, {"source": blank, "extra": b})

    assert result.run.status is RunStatus.COMPLETED_WITH_WARNINGS
    assert "The source file contains no words." in result.run.warnings
    assert result.ok


def test_cancelled_run_is_recorded_as_cancelled(runtime, tmp_path):
    _publish(runtime, DEMO_SLUG, DEMO_MANIFEST)
    a = _text(tmp_path, "a.txt", "one")
    event = threading.Event()
    event.set()

    result = runtime.runner.run(DEMO_SLUG, {"source": a}, cancel_event=event)

    assert result.run.status is RunStatus.CANCELLED
    assert result.run.status.label == "Cancelled"
    assert any(x.role == "run_log" for x in result.artifacts)


def test_unapproved_version_cannot_run(runtime, tmp_path):
    _publish(runtime, DEMO_SLUG, DEMO_MANIFEST, approve=False)
    with pytest.raises(ProcessRuntimeError):
        runtime.runner.run(DEMO_SLUG, {"source": _text(tmp_path, "a.txt", "x")})


def test_unknown_process_raises(runtime, tmp_path):
    with pytest.raises(RecordNotFoundError):
        runtime.runner.run("ghost_proc", {})


def test_process_without_registered_handler_cannot_run(runtime):
    _publish(runtime, "ghost_proc", {})
    with pytest.raises(ProcessRuntimeError, match="No handler"):
        runtime.runner.run("ghost_proc", {})


def test_handler_input_validation_error_fails_the_run(runtime, tmp_path):
    _publish(
        runtime,
        "reject_proc",
        {"inputs": [{"role": "source", "label": "Source"}]},
    )
    result = runtime.runner.run("reject_proc", {"source": _text(tmp_path, "a.txt", "x")})

    assert result.run.status is RunStatus.FAILED
    assert "Sheet 'Data'" in result.run.error
    assert "AssertionError" not in result.run.error  # the handler never ran
    assert len(runtime.repos.runs.list_inputs(result.run.id)) == 1  # input was still staged