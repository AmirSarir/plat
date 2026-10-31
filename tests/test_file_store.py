import hashlib

import pytest

from engops.infrastructure.filesystem.file_store import (
    FileStore,
    FileStoreError,
    sanitize_filename,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("report.xlsx", "report.xlsx"),
        ("a/b\\c.txt", "c.txt"),
        ("CON.txt", "_CON.txt"),
        ("bad:name?.csv", "bad_name_.csv"),
        ("  ..  ", "file"),
        ("نمونه.xlsx", "نمونه.xlsx"),
        ("name.", "name"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_limits_length():
    result = sanitize_filename("a" * 300 + ".xlsx")
    assert len(result) <= 120
    assert result.endswith(".xlsx")


def _source(tmp_path, data=b"abc", name="in.xlsx"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_add_file_copies_and_hashes(tmp_path):
    store = FileStore(tmp_path / "store")
    src = _source(tmp_path)
    info = store.add_file(src, "inputs")
    assert store.path_of(info.rel_path).read_bytes() == b"abc"
    assert info.sha256 == hashlib.sha256(b"abc").hexdigest()
    assert info.size_bytes == 3
    assert info.rel_path.startswith("inputs/") and info.rel_path.endswith("/in.xlsx")
    assert src.read_bytes() == b"abc"  # original untouched


def test_same_file_twice_never_overwrites(tmp_path):
    store = FileStore(tmp_path / "store")
    src = _source(tmp_path)
    a = store.add_file(src, "outputs")
    b = store.add_file(src, "outputs")
    assert a.rel_path != b.rel_path
    assert store.path_of(a.rel_path).exists() and store.path_of(b.rel_path).exists()


def test_missing_source_rejected(tmp_path):
    store = FileStore(tmp_path / "store")
    with pytest.raises(FileStoreError):
        store.add_file(tmp_path / "nope.xlsx", "inputs")


def test_unknown_category_rejected(tmp_path):
    store = FileStore(tmp_path / "store")
    with pytest.raises(ValueError):
        store.add_file(_source(tmp_path), "temp")


def test_path_of_rejects_traversal(tmp_path):
    store = FileStore(tmp_path / "store")
    with pytest.raises(FileStoreError):
        store.path_of("../outside.txt")


def test_verify_detects_tampering(tmp_path):
    store = FileStore(tmp_path / "store")
    info = store.add_file(_source(tmp_path), "inputs")
    assert store.verify(info.rel_path, info.sha256, info.size_bytes)
    store.path_of(info.rel_path).write_bytes(b"xyz")  # same size, different content
    assert not store.verify(info.rel_path, info.sha256, info.size_bytes)


def test_discard_removes_the_file_folder(tmp_path):
    store = FileStore(tmp_path / "store")
    info = store.add_file(_source(tmp_path), "inputs")
    folder = store.path_of(info.rel_path).parent
    store.discard(info.rel_path)
    assert not folder.exists()