from dataclasses import replace
from datetime import timedelta

import pytest

from engops.domain.common import new_id, utc_now
from engops.domain.errors import DuplicateRecordError, RecordNotFoundError, RepositoryError
from engops.domain.models import (
    OutputArtifact,
    Process,
    ProcessStatus,
    ProcessVersion,
    Run,
    RunInput,
    RunStatus,
    StoredFile,
)
from engops.infrastructure.database.connection import transaction


def make_process(slug="demo", name="Demo", **kw):
    now = utc_now()
    return Process(id=new_id(), slug=slug, name=name, created_at=now, updated_at=now, **kw)


def make_version(process_id, version="1.0.0", **kw):
    now = utc_now()
    return ProcessVersion(
        id=new_id(), process_id=process_id, version=version, created_at=now, updated_at=now, **kw
    )


def make_file(name="a.xlsx"):
    return StoredFile(
        id=new_id(),
        rel_path=f"inputs/{new_id()}/{name}",
        original_name=name,
        size_bytes=10,
        sha256="ab" * 32,
        created_at=utc_now(),
    )


def make_run(version_id, **kw):
    return Run(id=new_id(), process_version_id=version_id, started_at=utc_now(), **kw)


def _process_with_version(repos, slug="demo"):
    process = make_process(slug=slug)
    repos.processes.add(process)
    version = make_version(process.id)
    repos.versions.add(version)
    return process, version


def test_process_roundtrip_and_lookup(repos):
    p = make_process(slug="trs_report", name="TRS Report", purpose="Weekly", owner="Team A")
    repos.processes.add(p)
    assert repos.processes.get(p.id) == p
    assert repos.processes.get_by_slug("trs_report") == p
    assert repos.processes.get("missing") is None
    assert repos.processes.count() == 1


def test_duplicate_slug_rejected(repos):
    repos.processes.add(make_process(slug="same"))
    with pytest.raises(DuplicateRecordError):
        repos.processes.add(make_process(slug="same"))


def test_update_process(repos):
    p = make_process()
    repos.processes.add(p)
    updated = repos.processes.update(replace(p, name="Renamed", status=ProcessStatus.RETIRED))
    fetched = repos.processes.get(p.id)
    assert fetched.name == "Renamed"
    assert fetched.status is ProcessStatus.RETIRED
    assert fetched == updated
    with pytest.raises(RecordNotFoundError):
        repos.processes.update(make_process(slug="ghost"))


def test_list_excludes_retired_by_default(repos):
    active = make_process(slug="active_one", name="Active")
    retired = make_process(slug="retired_one", name="Retired", status=ProcessStatus.RETIRED)
    repos.processes.add(active)
    repos.processes.add(retired)
    assert [p.slug for p in repos.processes.list_all()] == ["active_one"]
    assert len(repos.processes.list_all(include_retired=True)) == 2


def test_version_manifest_roundtrip_and_unique(repos):
    p = make_process()
    repos.processes.add(p)
    manifest = {"inputs": [{"role": "visibility", "required": True}], "outputs": ["report"]}
    v = make_version(p.id, manifest=manifest)
    repos.versions.add(v)
    assert repos.versions.get(v.id).manifest == manifest
    with pytest.raises(DuplicateRecordError):
        repos.versions.add(make_version(p.id))  # same process + same version string


def test_approve_and_latest_approved(repos):
    p, v = _process_with_version(repos)
    assert repos.versions.latest_approved(p.id) is None
    approved = repos.versions.approve(v.id, "Reviewer")
    assert approved.approved and approved.approved_by == "Reviewer"
    assert approved.approved_at is not None
    assert repos.versions.get(v.id) == approved
    assert repos.versions.latest_approved(p.id) == approved
    assert repos.versions.approve(v.id, "Someone else").approved_by == "Reviewer"  # idempotent
    with pytest.raises(RecordNotFoundError):
        repos.versions.approve("ghost", "x")


def test_run_foreign_key_enforced(repos):
    with pytest.raises(RepositoryError):
        repos.runs.add(make_run("no-such-version"))


def test_run_lifecycle_with_inputs_and_artifacts(repos):
    _, v = _process_with_version(repos)
    f_in, f_out = make_file(), make_file("out.xlsx")
    repos.files.add(f_in)
    repos.files.add(f_out)

    run = make_run(v.id)
    repos.runs.add(run)
    assert repos.runs.get(run.id).status is RunStatus.RUNNING

    repos.runs.add_input(
        RunInput(
            id=new_id(),
            run_id=run.id,
            role="visibility",
            stored_file_id=f_in.id,
            original_path=r"D:\data\vis.xlsx",
        )
    )
    repos.runs.add_artifact(
        OutputArtifact(id=new_id(), run_id=run.id, role="report", stored_file_id=f_out.id)
    )

    finished = replace(
        run,
        status=RunStatus.COMPLETED_WITH_WARNINGS,
        finished_at=utc_now(),
        summary="2 of 3 steps",
        warnings=("Huawei old inventory missing",),
    )
    repos.runs.update(finished)

    got = repos.runs.get(run.id)
    assert got == finished
    assert got.status.label == "Completed with warnings"
    assert [i.role for i in repos.runs.list_inputs(run.id)] == ["visibility"]
    assert repos.runs.list_inputs(run.id)[0].original_path == r"D:\data\vis.xlsx"
    assert [a.stored_file_id for a in repos.runs.list_artifacts(run.id)] == [f_out.id]


def test_list_recent_filters_and_orders(repos):
    p1, v1 = _process_with_version(repos, slug="proc_one")
    p2, v2 = _process_with_version(repos, slug="proc_two")
    base = utc_now()
    r1 = replace(make_run(v1.id), started_at=base)
    r2 = replace(make_run(v2.id), started_at=base + timedelta(minutes=1))
    r3 = replace(make_run(v1.id), started_at=base + timedelta(minutes=2))
    for r in (r1, r2, r3):
        repos.runs.add(r)

    assert [r.id for r in repos.runs.list_recent()] == [r3.id, r2.id, r1.id]
    assert [r.id for r in repos.runs.list_recent(process_id=p1.id)] == [r3.id, r1.id]
    assert [r.id for r in repos.runs.list_recent(limit=1)] == [r3.id]
    assert repos.runs.count() == 3


def test_transaction_rolls_back_on_error(conn, repos):
    with pytest.raises(RuntimeError):
        with transaction(conn):
            repos.processes.add(make_process())
            raise RuntimeError("boom")
    assert repos.processes.count() == 0