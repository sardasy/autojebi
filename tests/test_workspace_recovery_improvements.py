import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update

from api.hwp_worker.progress import Progress
from api.workspace import receipts, service
from api.workspace.quote_recovery import AnalysisFailure, diagnose, matches
from api.workspace.source_needs import inventory, issues
from api.workspace.tables import jobs, workspaces
from api.workspace.worker import claim, run_once
from tests import test_workspace_v2 as workspace_fixtures

workspace = workspace_fixtures.workspace


def candidate(quote="납기 90일", document_id="source"):
    return {"text": "납기 확인", "quote": quote, "document_id": document_id,
            "locator": "1절", "category": "schedule", "mandatory": True}


@pytest.mark.parametrize("text,quote,state", [
    ("납기 90일", "납기 90일", "exact"),
    ("납기\n90일", "납기 90일", "whitespace"),
    ("납기 90일 / 납기 90일", "납기 90일", "ambiguous"),
    ("납기 90일", "납기 60일", "mismatch"),
    ("승인하지 않는다", "승인한다", "mismatch"),
])
def test_quote_diagnostics(text, quote, state):
    value = diagnose([candidate(quote)], [{"id": "source", "text": text}], 9)[0]
    assert value["status"] == state
    for match in value["matches"]:
        assert text[match["start"]:match["end"]] == match["quote"]


def test_missing_document_and_malformed_candidate():
    rows = diagnose([candidate(document_id="wrong"), None, {"token": "private"}], [], 1)
    assert [r["status"] for r in rows] == ["mismatch", "invalid_structure", "invalid_structure"]
    assert "private" not in str(rows)
    assert matches("hello", " ") == []


@pytest.fixture
def recovery_job(workspace, sqlite_engine, tmp_path):
    path = tmp_path / "workspace" / "source.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text("납기 90일. 제안요청서를 확인하세요.", encoding="utf-8")
    doc = {"id": "source", "name": "notice.txt", "role": "notice_source", "text": path.read_text(encoding="utf-8"),
           "storage_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    inputs = workspace["inputs"]
    inputs["documents"] = [doc]
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=inputs))
        ws = service.load(conn, "E2E-V2")
        job = service.create_job_record(conn, ws, "analyze", "diagnostic", {})
        conn.execute(update(jobs).where(jobs.c.id == job["id"]).values(status="failed",
            error={"code": "unverified_quote"}, result={"quote_diagnostics": diagnose([candidate()], [doc], 1)}))
    return job["id"]


def selection():
    return {"version": 1, "idempotency_key": "adopt-one", "note": "원문 대조",
            "items": [{"candidate_id": "0", "quote": "납기 90일", "start": 0, "locator": "1절"}]}


def test_adoption_idempotency_and_no_approval(client, recovery_job, sqlite_engine):
    path = f"/v2/notices/E2E-V2/jobs/{recovery_job}/adopt-requirements"
    body = selection()
    result = client.post(path, json=body)
    assert result.status_code == 200, result.text
    ws = result.json()
    assert ws["version"] == 2 and ws["decision"] == "pending"
    req = ws["inputs"]["requirements"][0]
    assert req["review_status"] == "pending" and req["compliance"] == "unassessed"
    assert client.post(path, json=body).json()["version"] == 2
    body["note"] = "different"
    assert client.post(path, json=body).status_code == 409
    with sqlite_engine.connect() as conn:
        assert conn.execute(select(jobs.c.status).where(jobs.c.id == recovery_job)).scalar() == "failed"


@pytest.mark.parametrize("field,value", [("quote", "납기 60일"), ("start", 1), ("candidate_id", "9")])
def test_adoption_rejects_invalid_span(client, recovery_job, field, value):
    body = selection()
    body["items"][0][field] = value
    result = client.post(f"/v2/notices/E2E-V2/jobs/{recovery_job}/adopt-requirements", json=body)
    assert result.status_code == 409
    assert client.get("/v2/notices/E2E-V2/workspace").json()["version"] == 1


def test_stale_adoption_and_changed_source(client, recovery_job, sqlite_engine):
    body = selection()
    body["version"] = 9
    path = f"/v2/notices/E2E-V2/jobs/{recovery_job}/adopt-requirements"
    assert client.post(path, json=body).status_code == 409
    with sqlite_engine.begin() as conn:
        ws = service.load(conn, "E2E-V2")
        ws["inputs"]["documents"][0]["text"] += " changed"
        conn.execute(update(workspaces).values(inputs=ws["inputs"]))
    assert client.post(path, json=selection()).json()["detail"]["code"] == "source_changed"


def test_source_need_api_and_recheck(client, recovery_job):
    ws = client.get("/v2/notices/E2E-V2/workspace").json()
    need = ws["source_needs"][0]
    assert need["name"] == "제안요청서" and need["state"] == "missing"
    body = {"version": 1, "items": [{"id": need["id"], "state": "linked", "document_id": "source",
            "resolution_quote": "제안요청서를 확인하세요.", "note": "test link"}]}
    result = client.put("/v2/notices/E2E-V2/source-needs", json=body)
    assert result.status_code == 200, result.text
    ws = result.json()
    assert ws["source_needs"][0]["state"] == "linked"
    ws["inputs"]["documents"][0]["text"] += "changed"
    assert issues(ws["inputs"])
    assert client.put("/v2/notices/E2E-V2/source-needs", json=body).status_code == 409


def test_source_need_merges_format_mentions_and_excludes_reference():
    docs = [{"id": str(i), "role": "notice_source", "text": "별도 제안요청서 참조"} for i in range(2)]
    docs.append({"id": "ref", "role": "company_reference", "text": "과업내용서"})
    needs = inventory({"documents": docs})
    assert len(needs) == 1 and len(needs[0]["mentions"]) == 2


def test_lane_claim_does_not_touch_other_lane(workspace, sqlite_engine):
    with sqlite_engine.begin() as conn:
        ws = service.load(conn, "E2E-V2")
        ext = service.create_job_record(conn, ws, "hwp", "external", {})
        local = service.create_job_record(conn, ws, "excel", "local", {})
    assert claim(sqlite_engine, "local")["id"] == local["id"]
    assert claim(sqlite_engine, "local") is None
    assert claim(sqlite_engine, "external")["id"] == ext["id"]


def test_failed_analysis_preserves_diagnostics(workspace, sqlite_engine, monkeypatch):
    from api.workspace import worker
    with sqlite_engine.begin() as conn:
        job = service.create_job_record(conn, service.load(conn, "E2E-V2"), "analyze", "failed", {})
    diagnostics = {"quote_diagnostics": [{"candidate_id": "0", "status": "mismatch", "matches": []}]}
    def execute(*args):
        raise AnalysisFailure(diagnostics)
    monkeypatch.setattr(worker, "execute", execute)
    run_once(sqlite_engine)
    with sqlite_engine.connect() as conn:
        saved = conn.execute(select(jobs).where(jobs.c.id == job["id"])).mappings().one()
    assert saved["status"] == "failed" and saved["result"] == diagnostics


def test_local_finishes_while_external_is_running(workspace, sqlite_engine, monkeypatch):
    from api.workspace import worker

    with sqlite_engine.begin() as conn:
        ws = service.load(conn, "E2E-V2")
        external = service.create_job_record(conn, ws, "hwp", "external-running", {})
        local = service.create_job_record(conn, ws, "package", "local-ready", {})
    claimed = claim(sqlite_engine, "external")
    assert claimed["id"] == external["id"]
    monkeypatch.setattr(worker, "execute", lambda *_: {"warnings": ["review required"]})
    assert run_once(sqlite_engine, lane="local")
    with sqlite_engine.connect() as conn:
        rows = {r["id"]: r for r in conn.execute(select(jobs)).mappings()}
    assert rows[local["id"]]["status"] == "succeeded"
    assert rows[external["id"]]["status"] == "running"
    assert rows[external["id"]]["claim_token"] == claimed["claim_token"]


def test_receipts_are_lane_local(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    for lane in ("local", "external"):
        receipts.save(receipts.Receipt(job_id=lane, claim_token=lane, notice_no="x", input_version=1,
            status="succeeded", result={}, error=None, completed_at=datetime.now(UTC), lane=lane))
    assert not receipts.pending()
    assert len(receipts.pending("local")) == len(receipts.pending("external")) == 1


def test_timeout_keeps_first_stage_during_cleanup(tmp_path):
    progress = Progress(tmp_path)
    with progress.operation("job-1"):
        progress.update("open", "Open")
        progress.mark_failure()
        progress.update("quit", "Quit")
    state = progress.snapshot()
    assert state["failure_stage"] == "open" and state["stage"] == "quit"
    assert state["failed_at"] and state["finished_at"] and progress.uncertain


def _analyze_job(sqlite_engine, recovery_job, existing, results):
    """Turn the fixture job into a succeeded analyze result on top of `existing` requirements."""
    with sqlite_engine.begin() as conn:
        ws = service.load(conn, "E2E-V2")
        ws["inputs"]["requirements"] = existing
        conn.execute(update(workspaces).values(inputs=ws["inputs"]))
        conn.execute(update(jobs).where(jobs.c.id == recovery_job).values(
            status="succeeded", error=None, result={"requirements": results}))
    return f"/v2/notices/E2E-V2/jobs/{recovery_job}/apply"


@pytest.mark.parametrize("result,added", [
    ({"text": "다른 표현", "quote": "납기 90일"}, 0),          # same quote, reworded text
    ({"text": "납기 확인", "quote": "제안요청서를 확인하세요."}, 0),  # same text, other quote
    ({"text": "납기 확인", "quote": "납기 90일"}, 0),          # exact duplicate
    ({"text": "제안요청서 확인", "quote": "제안요청서를 확인하세요."}, 1),
])
def test_apply_uses_the_adoption_duplicate_rule(client, recovery_job, sqlite_engine, result, added):
    existing = [{**candidate(), "id": "manual", "review_status": "pending", "compliance": "unassessed"}]
    path = _analyze_job(sqlite_engine, recovery_job, existing, [{**candidate(), **result}])
    response = client.post(path, json={"version": 1})
    assert response.status_code == 200, response.text
    ws = response.json()
    assert len(ws["inputs"]["requirements"]) == 1 + added
    assert ws["version"] == 1 + added  # nothing new must not create an input version


def test_apply_skips_duplicates_inside_one_result(client, recovery_job, sqlite_engine):
    first = candidate()
    path = _analyze_job(sqlite_engine, recovery_job, [], [first, {**first, "text": "다른 표현"},
        {**first, "text": "제안요청서 확인", "quote": "제안요청서를 확인하세요."}])
    ws = client.post(path, json={"version": 1}).json()
    assert [r["text"] for r in ws["inputs"]["requirements"]] == ["납기 확인", "제안요청서 확인"]
    assert all(r["review_status"] == "pending" for r in ws["inputs"]["requirements"])
