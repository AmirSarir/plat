import pytest

from engops.domain.errors import (
    DuplicateRecordError,
    RecordNotFoundError,
    RepositoryError,
    ValidationError,
)
from engops.infrastructure.filesystem.file_store import FileStore
from engops.services.file_service import FileService
from engops.services.process_catalog import ProcessCatalogService


def _source(tmp_path, data=b"hello"):
    path = tmp_path / "in.xlsx"
    path.write_bytes(data)
    return path


def _catalog(conn, repos):
    return ProcessCatalogService(conn, repos.processes, repos.versions)


def test_import_file_stores_and_records(tmp_path, conn, repos):
    service = FileService(FileStore(tmp_path / "store"), repos.files, conn)
    src = _source(tmp_path)
    stored = service.import_file(src, "inputs")
    assert repos.files.get(stored.id) == stored
    assert service.path_of(stored).read_bytes() == b"hello"
    assert service.verify(stored)
    assert src.read_bytes() == b"hello"


def test_import_file_cleans_up_when_db_insert_fails(tmp_path, conn):
    class FailingRepo:
        def add(self, stored):
            raise RepositoryError("boom")

        def get(self, file_id):
            return None

    service = FileService(FileStore(tmp_path / "store"), FailingRepo(), conn)
    with pytest.raises(RepositoryError):
        service.import_file(_source(tmp_path), "inputs")
    assert list((tmp_path / "store" / "inputs").iterdir()) == []


def test_register_process_validates_input(conn, repos):
    catalog = _catalog(conn, repos)
    with pytest.raises(ValidationError):
        catalog.register_process(slug="Bad Slug", name="X")
    with pytest.raises(ValidationError):
        catalog.register_process(slug="ok_slug", name="   ")


def test_register_duplicate_slug_rejected(conn, repos):
    catalog = _catalog(conn, repos)
    catalog.register_process(slug="trs_report", name="TRS Report")
    with pytest.raises(DuplicateRecordError):
        catalog.register_process(slug="trs_report", name="Another")
    assert repos.processes.count() == 1


def test_add_version_unknown_process(conn, repos):
    with pytest.raises(RecordNotFoundError):
        _catalog(conn, repos).add_version("ghost", "1.0.0")


def test_version_approval_flow(conn, repos):
    catalog = _catalog(conn, repos)
    process = catalog.register_process(slug="trs_report", name="TRS Report", owner="Team A")
    version = catalog.add_version(process.id, "1.0.0", {"inputs": []})
    assert not version.approved
    with pytest.raises(ValidationError):
        catalog.approve_version(version.id, "  ")
    approved = catalog.approve_version(version.id, "Reviewer")
    assert approved.approved
    assert repos.versions.latest_approved(process.id) == approved