"""Package only the verified byte snapshot, even if a file is replaced mid-write."""

import hashlib
import json
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import update

from api.workspace import execution, service
from api.workspace.errors import WorkspaceError
from api.workspace.output_plan import LAYOUT_WARNING
from api.workspace.tables import jobs
from tests.test_workspace_output_plan import approve, plan, seed_output
from tests.test_workspace_output_plan import prepared as prepared


@pytest.mark.parametrize("target", ["source", "hwp"])
def test_restored_file_swap_during_zip_write_cannot_replace_approved_package_bytes(
    client, sqlite_engine, tmp_path, prepared, monkeypatch, target,
):
    plan(client, prepared)
    with sqlite_engine.begin() as conn:
        state = service.load(conn, "OUTPUT-TEST")
        hwp = seed_output(conn, state, tmp_path, "hwp", [LAYOUT_WARNING])
        excel = seed_output(conn, state, tmp_path, "excel")
    assert approve(client, prepared, state["version"], hwp, layout_confirmed=True,
                   output_sha256=hwp["result"]["sha256"]).status_code == 200
    assert approve(client, prepared, state["version"], excel).status_code == 200
    if target == "source":
        document = state["inputs"]["documents"][0]
        path = Path(document["storage_path"])
        member = f"sources/{document['id']}{path.suffix}"
    else:
        path = Path(hwp["result"]["artifact"])
        member = f"outputs/{hwp['id']}{path.suffix}"
    original = path.read_bytes()
    changed = b"X" * len(original)
    assert changed != original
    original_open = zipfile.ZipFile.open
    swaps = []

    @contextmanager
    def replace_during_member_write(archive, name, mode="r", *args, **kwargs):
        writing_target = mode == "w" and getattr(name, "filename", name) == member
        with original_open(archive, name, mode, *args, **kwargs) as stream:
            if writing_target:
                # The old archive.write(path) read the now-replaced source after
                # entering this context, despite checking its earlier hash.
                path.write_bytes(changed)
                swaps.append(member)
            try:
                yield stream
            finally:
                if writing_target:
                    path.write_bytes(original)

    monkeypatch.setattr(zipfile.ZipFile, "open", replace_during_member_write)
    folder = tmp_path / "immutable-package"
    folder.mkdir()
    result = execution.run_package(sqlite_engine, {"notice_no": "OUTPUT-TEST",
        "input_version": state["version"], "snapshot": state["inputs"]}, folder)
    assert swaps == [member]
    assert path.read_bytes() == original
    assert result["warnings"] == []
    with zipfile.ZipFile(result["artifact"]) as archive:
        assert archive.read(member) == original
        manifest = json.loads(archive.read("manifest.json"))
        entry = next(item for item in manifest["files"]
                     if item.get("name") == member or (target == "hwp" and item.get("job_id") == hwp["id"]))
        assert entry["sha256"] == hashlib.sha256(archive.read(member)).hexdigest()
    with sqlite_engine.begin() as conn:
        package = service.create_job_record(conn, state, "package", service.uid(), {})
        conn.execute(update(jobs).where(jobs.c.id == package["id"]).values(status="succeeded", result=result))
    ready = client.post(prepared + "/reviews", json={"version": state["version"],
        "job_id": package["id"], "action": "ready", "note": "동일 바이트 패키지 최종 검토"})
    assert ready.status_code == 200, ready.text
    assert client.get(prepared + "/workspace").json()["ready"] is True


def test_source_changed_after_path_validation_is_rejected_before_packaging(
    client, sqlite_engine, tmp_path, prepared, monkeypatch,
):
    plan(client, prepared)
    with sqlite_engine.connect() as conn:
        state = service.load(conn, "OUTPUT-TEST")
    source = state["inputs"]["documents"][0]
    path = Path(source["storage_path"])
    original = path.read_bytes()
    checked_path = execution.source_path

    def replace_after_check(document):
        result = checked_path(document)
        if document["id"] == source["id"]:
            result.write_bytes(b"unverified replacement")
        return result

    monkeypatch.setattr(execution, "source_path", replace_after_check)
    folder = tmp_path / "rejected-package"
    folder.mkdir()
    try:
        with pytest.raises(WorkspaceError) as failure:
            execution.run_package(sqlite_engine, {"notice_no": "OUTPUT-TEST",
                "input_version": state["version"], "snapshot": state["inputs"]}, folder)
        assert failure.value.detail["code"] == "source_file_changed"
        with zipfile.ZipFile(folder / "review-package.zip") as archive:
            assert not any(name.startswith("sources/") for name in archive.namelist())
    finally:
        path.write_bytes(original)
