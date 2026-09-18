import hashlib
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update

from api.routers.notices import hwp_templates
from api.workspace import service
from api.workspace.execution import run_package
from api.workspace.output_plan import LAYOUT_WARNING
from api.workspace.tables import jobs, workspaces
from tests.test_workspace_safety import complete_inputs


@pytest.fixture
def prepared(client, sqlite_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    assert client.post("/v2/notices", json={"notice_no": "OUTPUT-TEST", "title": "TEST ONLY",
                       "source": "MANUAL", "raw": {}}).status_code == 200
    with sqlite_engine.begin() as conn:
        conn.execute(hwp_templates.insert().values(template_key="proposal_layout_v1", kind="proposal",
                     name="실무 서식", template_path="missing-test-template.hwp"))
    assert client.post("/v2/notices/OUTPUT-TEST/initialize").status_code == 200
    inputs = complete_inputs()
    inputs["notice"] = {"close_date": (service.now() + timedelta(days=30)).isoformat()}
    for doc in inputs["documents"]:
        path = tmp_path / (doc["id"] + ".txt")
        path.write_text(doc["text"], encoding="utf-8")
        doc.update(storage_path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=inputs, decision="participate"))
    return "/v2/notices/OUTPUT-TEST"


def plan(client, prefix, version=1):
    response = client.put(prefix + "/output-plan", json={"version": version,
                         "template_keys": ["proposal_layout_v1"], "note": "시험 공고 제안서 선택"})
    assert response.status_code == 200, response.text
    return response.json()


def test_manual_notice_preserves_explicit_deadline_and_institution(client):
    response = client.post("/v2/notices", json={"notice_no": "MANUAL-DEADLINE", "title": "TEST",
        "org_name": "시험기관", "close_date": "2099-10-03T14:30:00+09:00", "raw": {}})
    assert response.status_code == 200
    ws = client.post("/v2/notices/MANUAL-DEADLINE/initialize").json()
    assert ws["inputs"]["notice"]["org_name"] == "시험기관"
    # SQLite drops tzinfo from DateTime columns; raw preserves the declared offset.
    assert ws["inputs"]["raw"]["bidClseDt"] == "2099-10-03T14:30:00+09:00"
    assert "2099-10-03" in ws["inputs"]["notice"]["close_date"]
    assert client.post("/v2/notices", json={"notice_no": "INVALID-DEADLINE",
        "close_date": "2099-10-03T14:30:00"}).status_code == 422


def seed_output(conn, ws, folder, kind, warnings=None, **extra):
    path = folder / (service.uid() + ".bin")
    path.write_bytes(b"TEST ONLY generated output")
    result = {"artifact": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "warnings": warnings or [], "verified": True, **extra}
    job = service.create_job_record(conn, ws, kind, service.uid(),
                                   {"template_key": "proposal_layout_v1"})
    conn.execute(update(jobs).where(jobs.c.id == job["id"]).values(status="succeeded", result=result))
    return {**job, "status": "succeeded", "result": result}


def approve(client, prefix, version, job, **extra):
    return client.post(prefix + "/reviews", json={"version": version, "job_id": job["id"],
        "action": "approved", "note": "TEST ONLY 파일 검토", **extra})


def test_output_plan_versioned_validated_and_preserves_content_reviews(client, prepared):
    state = plan(client, prepared)
    assert state["version"] == 2
    assert state["inputs"]["output_plan"]["template_keys"] == ["proposal_layout_v1"]
    assert state["inputs"]["proposal_sections"][0]["review_status"] == "approved"
    assert plan(client, prepared, 2)["version"] == 2
    for keys in [[], ["unregistered"]]:
        response = client.put(prepared + "/output-plan", json={"version": 2,
                              "template_keys": keys, "note": "test"})
        assert response.status_code == 422
    assert client.put(prepared + "/output-plan", json={"version": 1,
        "template_keys": ["proposal_layout_v1"], "note": "old"}).status_code == 409


@pytest.mark.parametrize("change,code", [
    ({}, "layout_review_required"),
    ({"layout_confirmed": True, "output_sha256": "0" * 64}, "file_changed"),
])
def test_hwp_review_requires_exact_file_and_layout(client, sqlite_engine, tmp_path, prepared, change, code):
    state = plan(client, prepared)
    with sqlite_engine.begin() as conn:
        job = seed_output(conn, state, tmp_path, "hwp", [LAYOUT_WARNING])
    response = approve(client, prepared, 2, job, **change)
    assert response.status_code == 409 and response.json()["detail"]["code"] == code


@pytest.mark.parametrize("extra", [{"verified": False}, {"required_missing": ["name"]},
                                  {"remaining_placeholders": ["body"]}])
def test_layout_acknowledgment_cannot_override_invalid_output(client, sqlite_engine, tmp_path, prepared, extra):
    state = plan(client, prepared)
    with sqlite_engine.begin() as conn:
        job = seed_output(conn, state, tmp_path, "hwp", [LAYOUT_WARNING], **extra)
    response = approve(client, prepared, 2, job, layout_confirmed=True,
                       output_sha256=job["result"]["sha256"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "hwp_review_blocked"


def test_selected_layout_reaches_ready_then_invalidates_on_file_or_review_change(
    client, sqlite_engine, tmp_path, prepared,
):
    state = plan(client, prepared)
    with sqlite_engine.begin() as conn:
        state = service.load(conn, "OUTPUT-TEST")
        hwp = seed_output(conn, state, tmp_path, "hwp", [LAYOUT_WARNING])
        excel = seed_output(conn, state, tmp_path, "excel")
    folder = tmp_path / "before-review"
    folder.mkdir()
    waiting = run_package(sqlite_engine, {"notice_no": "OUTPUT-TEST", "input_version": 2,
                          "snapshot": state["inputs"]}, folder)
    assert LAYOUT_WARNING in waiting["warnings"]
    assert not any("HWP 생성물 없음" in w for w in waiting["warnings"])
    assert approve(client, prepared, 2, hwp, layout_confirmed=True,
                   output_sha256=hwp["result"]["sha256"]).status_code == 200
    reviewed = next(r for r in client.get(prepared + "/workspace").json()["reviews"] if r["job_id"] == hwp["id"])
    assert reviewed["layout_confirmed"] is True
    assert reviewed["output_sha256"] == hwp["result"]["sha256"]
    assert approve(client, prepared, 2, excel).status_code == 200
    folder = tmp_path / "after-review"
    folder.mkdir()
    result = run_package(sqlite_engine, {"notice_no": "OUTPUT-TEST", "input_version": 2,
                         "snapshot": state["inputs"]}, folder)
    assert result["warnings"] == []
    with sqlite_engine.begin() as conn:
        package = service.create_job_record(conn, state, "package", service.uid(), {})
        conn.execute(update(jobs).where(jobs.c.id == package["id"]).values(status="succeeded", result=result))
    ready_body = {"version": 2, "job_id": package["id"], "action": "ready", "note": "TEST ONLY final"}
    response = client.post(prepared + "/reviews", json=ready_body)
    assert response.status_code == 200, response.text
    assert client.get(prepared + "/workspace").json()["ready"] is True
    path = Path(hwp["result"]["artifact"])
    original = path.read_bytes()
    path.write_bytes(b"changed")
    assert client.get(prepared + "/workspace").json()["ready"] is False
    path.write_bytes(original)
    assert client.get(prepared + "/workspace").json()["ready"] is True
    with sqlite_engine.begin() as conn:
        seed_output(conn, state, tmp_path, "hwp", [LAYOUT_WARNING])
    assert client.get(prepared + "/workspace").json()["ready"] is False
    assert Path(result["artifact"]).is_file()


def test_empty_package_cannot_be_marked_ready(client, sqlite_engine, tmp_path, prepared):
    state = plan(client, prepared)
    with sqlite_engine.begin() as conn:
        package = seed_output(conn, state, tmp_path, "package", included_jobs=[])
    result = client.post(prepared + "/reviews", json={"version": 2, "job_id": package["id"],
                         "action": "ready", "note": "TEST empty"})
    assert result.status_code == 409 and result.json()["detail"]["code"] == "package_changed"
    with sqlite_engine.connect() as conn:
        assert conn.execute(select(jobs.c.status).where(jobs.c.id == package["id"])).scalar() == "succeeded"
