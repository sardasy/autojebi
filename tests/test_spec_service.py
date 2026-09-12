import copy
from contextlib import contextmanager

import pytest
from sqlalchemy import select, update

from api.main import app  # noqa: F401
from api.specifications import indexing, service
from api.specifications.models import SearchRequest, Specification
from api.specifications.tables import active_indexes, generations, spec_events
from api.specifications.validation import sha
from api.workspace import service as workspace
from api.workspace.tables import jobs, workspaces


@pytest.fixture
def spec_env(client, sqlite_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("SPEC_SEARCH_ENABLED", "true")
    monkeypatch.setenv("SPEC_SEARCH_ENV", "validation")
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    client.post("/v2/notices", json={"notice_no": "SPEC-TEST", "title": "TEST ONLY", "source": "TEST"})
    client.post("/v2/notices/SPEC-TEST/initialize")
    raw = "장치 지연 1ms 이하"
    source = tmp_path / "source.txt"
    source.write_text(raw, encoding="utf-8")
    import hashlib
    doc = {"id": "source", "name": "TEST.txt", "role": "notice_source", "text": raw,
        "storage_path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "confirmed": False, "text_origin": "manual_confirmed"}
    payload = Specification(target="장치", property="latency", kind="numeric", operator="le", value="1", unit="ms", raw=raw,
        source={"document_id": "source", "document_sha256": doc["sha256"], "text_sha256": sha(raw),
                "start": 0, "end": len(raw), "quote": raw, "locator": "p1"})
    with sqlite_engine.begin() as conn:
        ws = workspace.load(conn, "SPEC-TEST")
        inputs = copy.deepcopy(ws["inputs"])
        inputs["documents"] = [doc]
        inputs["requirements"] = [{"id": "req", "document_id": "source", "text": raw, "quote": raw,
            "locator": "p1", "category": "technical", "mandatory": True, "review_status": "pending", "compliance": "unassessed"}]
        row = service.persist(conn, ws, "req", payload, "TEST ONLY")
        inputs["specifications"] = {"req": {"id": row["id"], "revision": 1, "payload": row["payload"], "validation": row["validation"]}}
        conn.execute(update(workspaces).where(workspaces.c.notice_no == "SPEC-TEST").values(inputs=inputs))
    return row, payload, doc


def test_get_put_cas_history_and_auth(client, sqlite_engine, spec_env, monkeypatch):
    row, payload, _ = spec_env
    path = f"/v2/notices/SPEC-TEST/specifications/{row['id']}"
    first = client.get(path)
    assert first.status_code == 200
    assert first.json()["index_state"]["status"] == "not_indexed"
    etag = first.headers["etag"]
    assert etag == first.json()["etag"]
    body = {"version": 1, "payload": payload.model_dump(), "note": "TEST correction"}
    assert client.put(path, json=body).status_code == 428
    assert client.put(path, json=body, headers={"If-Match": '"old"'}).status_code == 412
    assert client.put(path, json={**body, "version": 2}, headers={"If-Match": etag}).status_code == 409
    response = client.put(path, json=body, headers={"If-Match": etag})
    assert response.status_code == 200, response.text
    assert response.json()["input_version"] == 2
    assert client.put(path, json=body, headers={"If-Match": etag}).status_code == 412
    assert client.get(path).headers["etag"] != etag
    with sqlite_engine.begin() as conn:
        assert len(conn.execute(select(spec_events)).all()) == 2
        ws = workspace.load(conn, "SPEC-TEST")
        assert ws["decision"] == "pending" and ws["inputs"]["requirements"][0]["compliance"] == "unassessed"
    from api.config import settings
    monkeypatch.setattr(settings, "api_key", "TEST-private")
    assert client.get(path).status_code in {401, 403}


def test_disabled_no_projection_and_summary_consistent(client, spec_env, monkeypatch):
    ws = client.get("/v2/notices/SPEC-TEST/workspace").json()
    listing = client.get("/v2/notices/SPEC-TEST/specifications").json()
    assert ws["spec_compliance"] == listing["spec_compliance"] == "미확인"
    assert ws["unresolved_spec_count"] == 1
    monkeypatch.setenv("SPEC_SEARCH_ENV", "production")
    assert client.get("/v2/notices/SPEC-TEST/specifications").json()["items"] == []
    assert client.post("/v2/notices/SPEC-TEST/spec-search", json={"query": "장치"}).status_code == 503


def test_source_mismatch_cannot_be_saved(client, spec_env):
    row, payload, _ = spec_env
    path = f"/v2/notices/SPEC-TEST/specifications/{row['id']}"
    etag = client.get(path).headers["etag"]
    body = payload.model_dump()
    body["source"]["text_sha256"] = "b" * 64
    assert client.put(path, headers={"If-Match": etag}, json={"version": 1, "payload": body, "note": "bad"}).status_code == 409


def prepare_job(engine, doc, tmp_path):
    import hashlib
    quote = "장치 지연 999.97μs"
    path = tmp_path / "reference.txt"
    path.write_text(quote, encoding="utf-8")
    evidence = {**doc, "id": "evidence", "role": "company_reference", "text": quote,
                "storage_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    with engine.begin() as conn:
        ws = workspace.load(conn, "SPEC-TEST")
        inputs = copy.deepcopy(ws["inputs"])
        inputs["documents"].append(evidence)
        conn.execute(update(workspaces).where(workspaces.c.notice_no == ws["notice_no"]).values(inputs=inputs))
        job = workspace.create_job_record(conn, {**ws, "inputs": inputs}, "spec_index", "TEST-index", {})
        conn.execute(update(jobs).where(jobs.c.id == job["id"]).values(status="running", claim_token="TEST-claim"))
    return {**job, "claim_token": "TEST-claim"}


def test_partial_build_retries_only_failed_store_and_stale_search(sqlite_engine, spec_env, tmp_path, monkeypatch):
    _, _, doc = spec_env
    job = prepare_job(sqlite_engine, doc, tmp_path)
    monkeypatch.setenv("SPEC_BGE_REVISION", "a" * 40)
    monkeypatch.setenv("SPEC_BGE_SNAPSHOT", "TEST")
    @contextmanager
    def missing(*args):
        raise RuntimeError("private detail not persisted")
        yield
    monkeypatch.setattr(indexing, "graph_adapter", missing)
    monkeypatch.setattr(indexing, "vector_adapter", missing)
    monkeypatch.setattr(indexing, "embedder", lambda *a: (_ for _ in ()).throw(RuntimeError("missing")))
    result = indexing.build(sqlite_engine, job)
    assert result["stores"]["lexical"]["status"] == "succeeded"
    assert result["stores"]["graph"]["code"] == "graph_unavailable"
    assert "private" not in str(result)
    with sqlite_engine.begin() as conn:
        assert conn.execute(select(active_indexes)).first() is None
    retry = indexing.build(sqlite_engine, job)
    assert retry["generation"] == result["generation"]
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).where(workspaces.c.notice_no == "SPEC-TEST").values(version=2))
        conn.execute(update(jobs).where(jobs.c.id == job["id"]).values(input_version=2))
    job["input_version"] = 2
    new_version = indexing.build(sqlite_engine, job)
    assert new_version["generation"] != result["generation"]
    result = new_version
    hits = indexing.search(sqlite_engine, "SPEC-TEST", SearchRequest(query="장치 지연", requirement_id="req"), generation_id=result["generation"])
    assert hits["degraded"] and hits["groups"]["references"]
    assert hits["groups"]["references"][0]["compliance"] == "unassessed"
    with sqlite_engine.begin() as conn:
        ws = workspace.load(conn, "SPEC-TEST")
        inputs = copy.deepcopy(ws["inputs"])
        inputs["documents"][1]["confirmed"] = True
        conn.execute(update(workspaces).values(inputs=inputs))
    stale = indexing.search(sqlite_engine, "SPEC-TEST", SearchRequest(query="장치"), generation_id=result["generation"])
    assert stale["groups"]["references"] == []


def test_late_claim_cannot_publish_or_overwrite(sqlite_engine, spec_env, tmp_path, monkeypatch):
    job = prepare_job(sqlite_engine, spec_env[2], tmp_path)
    monkeypatch.setenv("SPEC_BGE_REVISION", "a" * 40)
    from fastapi import HTTPException
    with sqlite_engine.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.id == job["id"]).values(claim_token="replacement"))
    with pytest.raises(HTTPException):
        indexing.build(sqlite_engine, job)
    with sqlite_engine.begin() as conn:
        assert conn.execute(select(generations)).first() is None


def test_manual_candidate_uses_existing_adoption_path(client, spec_env):
    _, payload, _ = spec_env
    candidate = payload.model_dump(exclude={"source", "raw", "mandatory", "uncertainty", "lower_inclusive", "upper_inclusive"})
    response = client.post("/v2/notices/SPEC-TEST/requirements", json={"version": 1, "text": payload.raw,
        "document_id": "source", "quote": payload.raw, "locator": "p1", "category": "technical", "mandatory": True,
        "specification": candidate})
    assert response.status_code == 200, response.text
    assert len(client.get("/v2/notices/SPEC-TEST/specifications").json()["items"]) == 2


def test_compliance_aggregation_requires_review_validity_and_complete_source(sqlite_engine, spec_env):
    with sqlite_engine.begin() as conn:
        inputs = copy.deepcopy(workspace.load(conn, "SPEC-TEST")["inputs"])
    evidence = {"id": "proof", "role": "product_evidence", "confirmed": True, "text": "장치 지연 0.9ms",
                "company_asset": {"active": True, "no_expiry": True}}
    inputs["documents"].append(evidence)
    inputs["source_reviewed"] = True
    req = inputs["requirements"][0]
    req.update(review_status="accepted", compliance="meets", proposed_value="0.9ms",
               evidence_id="proof", evidence_quote=evidence["text"], evidence_locator="TEST line 1")
    assert service.summary(inputs)["spec_compliance"] == "충족"
    second = {**req, "id": "second", "review_status": "pending", "compliance": "unassessed"}
    inputs["requirements"].append(second)
    assert service.summary(inputs)["spec_compliance"] == "일부미확인"
    assert service.summary(inputs)["unresolved_spec_count"] == 1
    second["compliance"] = "does_not_meet"
    assert service.summary(inputs)["spec_compliance"] == "불충족"
    inputs["requirements"].pop()
    evidence.pop("company_asset")
    assert service.summary(inputs)["spec_compliance"] == "미확인"
    evidence["company_asset"] = {"active": True, "no_expiry": True}
    inputs["raw"] = {"ntceSpecFileNm1": "missing-task-description.pdf"}
    assert not service.summary(inputs)["source_complete"]
    assert service.summary(inputs)["spec_compliance"] == "미확인"
