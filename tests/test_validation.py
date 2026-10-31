from pathlib import Path

from engops.process_runtime.demo import DEMO_MANIFEST
from engops.process_runtime.manifest import ProcessManifest
from engops.process_runtime.validation import Severity, validate_inputs

MANIFEST = ProcessManifest.from_dict(DEMO_MANIFEST)


def _file(tmp_path, name="a.txt", data="hi"):
    path = tmp_path / name
    path.write_text(data, encoding="utf-8")
    return path


def test_missing_required_input_is_an_error():
    report = validate_inputs(MANIFEST, {})
    assert report.has_errors
    assert any("Source text file" in e.message for e in report.errors)


def test_unknown_role_is_an_error(tmp_path):
    f = _file(tmp_path)
    report = validate_inputs(MANIFEST, {"source": f, "bogus": f})
    assert any("bogus" in e.message for e in report.errors)


def test_wrong_extension_is_an_error(tmp_path):
    report = validate_inputs(MANIFEST, {"source": _file(tmp_path, "a.xlsx")})
    assert any(".txt" in e.message for e in report.errors)


def test_empty_file_is_an_error(tmp_path):
    report = validate_inputs(MANIFEST, {"source": _file(tmp_path, data="")})
    assert any("empty" in e.message for e in report.errors)


def test_nonexistent_file_is_an_error(tmp_path):
    report = validate_inputs(MANIFEST, {"source": Path(tmp_path / "nope.txt")})
    assert any("not found" in e.message for e in report.errors)


def test_missing_optional_input_is_info_only(tmp_path):
    report = validate_inputs(MANIFEST, {"source": _file(tmp_path)})
    assert not report.has_errors
    assert [i.severity for i in report.issues] == [Severity.INFO]
    assert "Second text file" in report.issues[0].message


def test_clean_inputs_produce_no_issues(tmp_path):
    f = _file(tmp_path)
    assert validate_inputs(MANIFEST, {"source": f, "extra": f}).issues == ()