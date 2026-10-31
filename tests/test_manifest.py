import pytest

from engops.process_runtime.demo import DEMO_MANIFEST
from engops.process_runtime.errors import ManifestError
from engops.process_runtime.manifest import ProcessManifest


def test_demo_manifest_parses_and_roundtrips():
    manifest = ProcessManifest.from_dict(DEMO_MANIFEST)
    assert [i.role for i in manifest.inputs] == ["source", "extra"]
    assert manifest.input_spec("extra").required is False
    assert ProcessManifest.from_dict(manifest.to_dict()) == manifest


def test_empty_legacy_manifest_is_valid():
    manifest = ProcessManifest.from_dict({"inputs": [], "outputs": []})
    assert manifest.operations == ()


@pytest.mark.parametrize(
    "data",
    [
        {"inputs": [{"role": "a"}, {"role": "a"}]},
        {"inputs": [{"role": "Bad Role"}]},
        {"inputs": [{"role": "a"}], "operations": [{"id": "op", "requires": ["ghost"]}]},
        {"inputs": [{"role": "a", "extensions": ["xlsx"]}]},
        {"operations": [{"id": "op"}, {"id": "op"}]},
    ],
)
def test_invalid_manifests_rejected(data):
    with pytest.raises(ManifestError):
        ProcessManifest.from_dict(data)


def test_plan_with_all_inputs_enables_everything():
    manifest = ProcessManifest.from_dict(DEMO_MANIFEST)
    plan = manifest.plan(["source", "extra"])
    assert [op.id for op in plan.enabled] == ["summarize", "compare"]
    assert plan.skipped == ()


def test_plan_skips_only_operations_with_missing_inputs():
    manifest = ProcessManifest.from_dict(DEMO_MANIFEST)
    plan = manifest.plan(["source"])
    assert [op.id for op in plan.enabled] == ["summarize"]
    assert [s.operation_id for s in plan.skipped] == ["compare"]
    assert "Second text file" in plan.skipped[0].reason