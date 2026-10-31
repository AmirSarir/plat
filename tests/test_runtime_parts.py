import threading

import pytest

from engops.process_runtime.contracts import BaseProcessHandler, ProcessContext, RunLog
from engops.process_runtime.errors import ProcessCancelled, ProcessRuntimeError
from engops.process_runtime.manifest import ProcessManifest
from engops.process_runtime.registry import HandlerRegistry


class _Handler(BaseProcessHandler):
    slug = "h_one"

    def run(self, ctx):
        pass


def test_registry_registers_and_returns_handler():
    registry = HandlerRegistry()
    handler = _Handler()
    registry.register(handler)
    assert registry.get("h_one") is handler
    assert registry.slugs() == ["h_one"]


def test_registry_rejects_duplicates():
    registry = HandlerRegistry()
    registry.register(_Handler())
    with pytest.raises(ProcessRuntimeError):
        registry.register(_Handler())


def test_registry_unknown_slug():
    with pytest.raises(ProcessRuntimeError):
        HandlerRegistry().get("ghost")


def test_registry_rejects_non_handlers():
    with pytest.raises(ProcessRuntimeError):
        HandlerRegistry().register(object())


def _ctx(tmp_path, event=None):
    manifest = ProcessManifest.from_dict(
        {
            "outputs": [{"role": "out", "label": "Out"}],
            "operations": [{"id": "op1", "label": "Operation one"}],
        }
    )
    out = tmp_path / "out"
    out.mkdir()
    return ProcessContext(
        run_id="r1",
        manifest=manifest,
        inputs={},
        plan=manifest.plan([]),
        output_dir=out,
        run_log=RunLog(),
        cancel_event=event,
    )


def test_new_output_path_never_collides(tmp_path):
    ctx = _ctx(tmp_path)
    first = ctx.new_output_path("a.txt")
    second = ctx.new_output_path("a.txt")
    assert first.name == "a.txt"
    assert second.name == "a (2).txt"


def test_add_output_rejects_undeclared_role(tmp_path):
    ctx = _ctx(tmp_path)
    path = ctx.new_output_path("x.txt")
    path.write_text("x")
    with pytest.raises(ProcessRuntimeError):
        ctx.add_output("nope", path)


def test_add_output_rejects_files_outside_output_folder(tmp_path):
    ctx = _ctx(tmp_path)
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("x")
    with pytest.raises(ProcessRuntimeError):
        ctx.add_output("out", elsewhere)


def test_check_cancelled_follows_the_event(tmp_path):
    event = threading.Event()
    ctx = _ctx(tmp_path, event)
    ctx.check_cancelled()  # not set: nothing happens
    event.set()
    with pytest.raises(ProcessCancelled):
        ctx.check_cancelled()