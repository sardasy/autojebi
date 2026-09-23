"""Template provenance must hold at artifact approval and every final readiness check."""

import hashlib
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import update

from api.db.tables import hwp_templates
from api.workspace import service
from api.workspace.executors.package import run_package
from api.workspace.tables import jobs, workspaces
from api.workspace.template_provenance import (
    inspect_provenance,
    metadata_path,
    register_source_form,
    write_skeleton_metadata,
)
from tests.test_workspace_hwp_validation import hwp_bytes
from tests.test_workspace_output_plan import approve, seed_output
from tests.test_workspace_safety import complete_inputs


@pytest.fixture
def provenance_workspace(client, sqlite_engine, tmp_path, monkeypatch, request):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HWP_TEMPLATE_ROOT", str(tmp_path))
    template_path = tmp_path / "test-only-template.hwp"
    template_path.write_bytes(hwp_bytes())
    template = {"template_key": "bid_form", "template_path": str(template_path)}
    checksum = hashlib.sha256(template_path.read_bytes()).hexdigest()
    mode = request.param
    if mode == "validation_only":
        write_skeleton_metadata(template_path, "bid_form", checksum, "test-only")
    elif mode == "reviewed_source":
        register_source_form(template, checksum, source_reference="TEST ONLY synthetic source",
                             reviewer_id="test-reviewer", review_note="TEST ONLY source attestation",
                             human_reviewed=True)
    with sqlite_engine.begin() as conn:
        conn.execute(hwp_templates.insert().values(**template, kind="bid_form", name="TEST ONLY"))
    prefix = "/v2/notices/PROVENANCE-REVIEW"
    assert client.post("/v2/notices", json={"notice_no": "PROVENANCE-REVIEW",
        "title": "TEST ONLY", "raw": {}}).status_code == 200
    assert client.post(prefix + "/initialize").status_code == 200
    inputs = complete_inputs()
    inputs["notice"] = {"close_date": (service.now() + timedelta(days=30)).isoformat()}
    for doc in inputs["documents"]:
        path = tmp_path / (doc["id"] + ".txt")
        path.write_text(doc["text"], encoding="utf-8")
        doc.update(storage_path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=inputs, decision="participate"))
    response = client.put(prefix + "/output-plan", json={"version": 1,
        "template_keys": ["bid_form"], "note": "TEST ONLY one template"})
    assert response.status_code == 200, response.text
    extra = {} if mode == "legacy_default" else {
        "template_key": "bid_form", "template_sha256": checksum,
        "template_provenance": inspect_provenance(template),
    }
    with sqlite_engine.begin() as conn:
        ws = service.load(conn, "PROVENANCE-REVIEW")
        hwp = seed_output(conn, ws, tmp_path, "hwp", **extra)
        # Legacy outputs carry the template key only in parameters.
        hwp["parameters"] = {"template_key": "bid_form"}
        conn.execute(update(jobs).where(jobs.c.id == hwp["id"]).values(parameters=hwp["parameters"]))
        excel = seed_output(conn, ws, tmp_path, "excel")
    return prefix, ws, hwp, excel, template_path


@pytest.mark.parametrize("provenance_workspace", ["validation_only", "legacy_default"], indirect=True)
def test_file_and_layout_acknowledgment_cannot_approve_skeleton_or_unclassified_default(
    client, provenance_workspace,
):
    prefix, ws, hwp, _, _ = provenance_workspace
    response = approve(client, prefix, ws["version"], hwp, layout_confirmed=True,
                       output_sha256=hwp["result"]["sha256"])
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "hwp_review_blocked"
    assert not any(review["action"] == "approved" for review in
                   client.get(prefix + "/workspace").json()["reviews"])


@pytest.mark.parametrize("provenance_workspace", ["validation_only", "legacy_default"], indirect=True)
def test_legacy_approval_and_warning_free_package_do_not_bypass_current_provenance(
    client, sqlite_engine, tmp_path, provenance_workspace,
):
    prefix, ws, hwp, excel, _ = provenance_workspace
    exports = tmp_path / "exports"
    exports.mkdir()
    with sqlite_engine.begin() as conn:
        for job in (hwp, excel):
            service.audit(conn, ws, "approved", "TEST ONLY historical approval",
                {"sha256": job["result"]["sha256"], "layout_confirmed": True}, job["id"])
        historical = seed_output(conn, ws, exports, "package", included_jobs=[hwp["id"], excel["id"]])
    response = client.post(prefix + "/reviews", json={"version": ws["version"],
        "job_id": historical["id"], "action": "ready", "note": "TEST ONLY current gate"})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "package_changed"
    with sqlite_engine.begin() as conn:
        service.audit(conn, ws, "ready", "TEST ONLY historical final approval",
                      {"sha256": historical["result"]["sha256"]}, historical["id"])
    assert client.get(prefix + "/workspace").json()["ready"] is False
    assert client.get(f"/v2/jobs/{historical['id']}/download").status_code == 200
    folder = tmp_path / "new-package"
    folder.mkdir()
    regenerated = run_package(sqlite_engine, {"notice_no": ws["notice_no"],
        "input_version": ws["version"], "snapshot": ws["inputs"]}, folder)
    assert f"생성물 검토 승인 필요: {hwp['id']}" in regenerated["warnings"]


@pytest.mark.parametrize("provenance_workspace", ["reviewed_source"], indirect=True)
def test_approved_source_form_reaches_ready_but_changed_origin_record_invalidates_it(
    client, sqlite_engine, tmp_path, provenance_workspace,
):
    prefix, ws, hwp, excel, template_path = provenance_workspace
    assert approve(client, prefix, ws["version"], hwp, layout_confirmed=True,
                   output_sha256=hwp["result"]["sha256"]).status_code == 200
    assert approve(client, prefix, ws["version"], excel).status_code == 200
    folder = tmp_path / "reviewed-package"
    folder.mkdir()
    result = run_package(sqlite_engine, {"notice_no": ws["notice_no"],
        "input_version": ws["version"], "snapshot": ws["inputs"]}, folder)
    assert result["warnings"] == []
    with sqlite_engine.begin() as conn:
        package = service.create_job_record(conn, ws, "package", service.uid(), {})
        conn.execute(update(jobs).where(jobs.c.id == package["id"]).values(status="succeeded", result=result))
    response = client.post(prefix + "/reviews", json={"version": ws["version"],
        "job_id": package["id"], "action": "ready", "note": "TEST ONLY final review"})
    assert response.status_code == 200, response.text
    assert client.get(prefix + "/workspace").json()["ready"] is True
    sidecar = metadata_path(template_path)
    sidecar.write_bytes(sidecar.read_bytes() + b"\n")
    changed = client.get(prefix + "/workspace").json()
    assert changed["source_changed"] is False  # Same template bytes; origin record changed separately.
    assert changed["ready"] is False
    assert Path(result["artifact"]).is_file()
