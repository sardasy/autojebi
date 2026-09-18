"""Opt-in isolated PG/Neo4j/BGE integration; never a production corpus benchmark."""
import os
import uuid
from contextlib import closing

import pytest
from sqlalchemy import create_engine, text

from api.specifications.retrieval import (
    BgeM3Embedder,
    GraphEvidence,
    GraphRequirement,
    Neo4jEvidenceAdapter,
    QdrantEvidenceAdapter,
    TextEvidence,
    build_lexical_query,
    ensure_graph_schema,
)

pytestmark = pytest.mark.skipif(os.getenv("SPEC_LIVE_TEST") != "true", reason="isolated live opt-in")


def test_fresh_postgres_migration_and_real_lexical(tmp_path):
    from alembic.config import Config

    from alembic import command
    url = os.environ["SPEC_TEST_DATABASE_URL"]
    engine = create_engine(url)
    assert engine.url.database == "spec_validation" and engine.url.port == 15433
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    # Alembic env reads DATABASE_URL; override only this isolated test process.
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(config, "head")
        with engine.begin() as conn:
            assert conn.execute(text("select version_num from alembic_version")).scalar() == "0017_spec_search"
            conn.execute(text("CREATE TEMP TABLE spec_search_chunks (generation_id text,id text,quote text,identifiers json,payload json)"))
            conn.execute(text("INSERT INTO spec_search_chunks VALUES ('g','a','CAN 2.0B','[\"can 2.0b\"]','{}'),('g','b','CAN 2.0A','[\"can 2.0a\"]','{}')"))
            found = conn.execute(build_lexical_query("CAN", generation_id="g", identifiers=["CAN 2.0B"])).mappings().all()
            assert [r["id"] for r in found] == ["a", "b"]
        command.downgrade(config, "0016_company_assets")
        command.upgrade(config, "head")
    finally:
        if old is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old
        engine.dispose()


def test_real_graph_relations_and_idempotent_upsert():
    from neo4j import GraphDatabase
    generation = "test-" + str(uuid.uuid4())
    with GraphDatabase.driver(os.environ["SPEC_NEO4J_URI"], auth=("neo4j", os.environ["SPEC_NEO4J_PASSWORD"]),
                             max_transaction_retry_time=0) as driver:
        ensure_graph_schema(driver, "neo4j")
        ensure_graph_schema(driver, "neo4j")
        adapter = Neo4jEvidenceAdapter(driver, database="neo4j", generation_id=generation)
        requirements = [GraphRequirement(requirement_id="test-requirement", notice_no="test-notice",
            document_id="test-notice-source", property="latency", target="Device-1.0", source_sha256="a" * 64)]
        assert adapter.upsert_requirements(requirements) == 1
        assert adapter.upsert_requirements(requirements) == 1
        rows = [GraphEvidence(evidence_id="a", group="reference", document_id="test-source", properties=("latency",), exact_identifiers=("CAN 2.0B",), targets=("Device-1.0",))]
        assert adapter.upsert(rows) == 1
        assert adapter.upsert(rows) == 1 and adapter.count() == 1
        assert adapter.read(properties=["latency"])[0].evidence_id == "a"
        assert adapter.read(["CAN 2.0A"]) == ()
        with driver.session(database="neo4j") as session:
            result = session.run("""
                MATCH (:SpecNotice {generation_id: $generation, notice_no: 'test-notice'})
                      -[:REQUIRES]->(r:SpecRequirement {generation_id: $generation})
                      -[:ABOUT]->(p:SpecProduct {generation_id: $generation, value: 'device-1.0'})
                MATCH (:SpecEvidence {generation_id: $generation, evidence_id: 'a'})-[:ABOUT]->(p)
                MATCH (r)-[:REQUIRES_PROPERTY]->(:SpecProperty {generation_id: $generation, value: 'latency'})
                MATCH (r)-[:SOURCED_FROM]->(:SpecDocument {generation_id: $generation, document_id: 'test-notice-source'})
                RETURN count(DISTINCT r) AS count
            """, generation=generation).single()
            assert result["count"] == 1


def test_real_bge_qdrant_dense_roundtrip():
    from qdrant_client import QdrantClient
    if not os.getenv("SPEC_BGE_SNAPSHOT"):
        pytest.skip("BGE-M3 local snapshot not provisioned")
    model = BgeM3Embedder(snapshot_path=os.environ["SPEC_BGE_SNAPSHOT"], revision=os.environ["SPEC_BGE_REVISION"])
    model.load_local()
    with closing(QdrantClient(url=os.environ["SPEC_QDRANT_URL"])) as client:
        adapter = QdrantEvidenceAdapter(client, generation_id="test-" + str(uuid.uuid4()), revision=model.revision)
        adapter.ensure_collection()
        assert adapter.index([TextEvidence(evidence_id="timing", group="reference", text="장치 지연 999.97μs")], embedder=model) == 1
        assert adapter.count() == 1
        assert adapter.query("장치 지연 1ms 이하", embedder=model)[0].evidence_id == "timing"


def test_real_queue_hybrid_and_concurrent_correction(tmp_path, monkeypatch):
    import hashlib
    from concurrent.futures import ThreadPoolExecutor

    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from sqlalchemy import select, update

    from api.config import settings
    from api.main import app
    from api.specifications import indexing, service
    from api.specifications.models import Correction, SearchRequest, Specification
    from api.specifications.tables import active_indexes
    from api.specifications.validation import sha
    from api.workspace import service as workspace
    from api.workspace.tables import jobs, workspaces
    from api.workspace.worker import run_once

    if not os.getenv("SPEC_BGE_SNAPSHOT"):
        pytest.skip("Local model required for real hybrid pipeline")
    indexing.provision_graph_schema()
    engine = create_engine(os.environ["SPEC_TEST_DATABASE_URL"])
    assert engine.url.database == "spec_validation" and engine.url.port == 15433
    with engine.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.notice_no.like("SPEC-LIVE-%"), jobs.c.kind == "spec_index",
            jobs.c.status == "queued").values(status="blocked", error={"code": "previous_synthetic_test_aborted"}))
    monkeypatch.setattr("api.db.get_engine", lambda: engine)
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    client = TestClient(app)
    notice = "SPEC-LIVE-" + str(uuid.uuid4())[:8]
    assert client.post("/v2/notices", json={"notice_no": notice, "title": "SYNTHETIC integration", "source": "TEST"}).status_code == 200
    assert client.post(f"/v2/notices/{notice}/initialize").status_code == 200
    docs = []
    for key, role, raw in (("source", "notice_source", "장치 지연 1ms 이하"),
                           ("good", "product_evidence", "장치 지연 999.97μs"),
                           ("bad", "product_evidence", "장치 지연 1000.01μs")):
        path = tmp_path / (key + ".txt")
        path.write_text(raw, encoding="utf-8")
        docs.append({"id": key, "name": "TEST " + key, "text": raw, "role": role, "confirmed": role != "notice_source",
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "storage_path": str(path), "text_origin": "manual_confirmed",
                     "company_asset": {"active": True, "no_expiry": True} if role == "product_evidence" else None})
    raw = docs[0]["text"]
    payload = Specification(target="장치", property="latency", kind="numeric", operator="le", value="1", unit="ms", raw=raw,
        source={"document_id": "source", "document_sha256": docs[0]["sha256"], "text_sha256": sha(raw),
                "start": 0, "end": len(raw), "quote": raw, "locator": "TEST page 1"})
    with engine.begin() as conn:
        ws = workspace.load(conn, notice)
        inputs = {**ws["inputs"], "documents": docs, "requirements": [{"id": "req", "text": raw, "quote": raw,
            "document_id": "source", "locator": "TEST page 1", "category": "technical", "mandatory": True,
            "compliance": "unassessed", "review_status": "pending"}]}
        row = service.persist(conn, {**ws, "inputs": inputs}, "req", payload, "TEST only")
        inputs["specifications"] = {"req": {"id": row["id"], "revision": 1, "payload": row["payload"], "validation": row["validation"]}}
        conn.execute(update(workspaces).where(workspaces.c.notice_no == notice).values(inputs=inputs))
    token = service.etag(row, 1)
    body = Correction(version=1, payload=payload, note="TEST simultaneous correction")
    def correct_once():
        try:
            with engine.begin() as conn:
                service.correct(conn, notice, row["id"], body, token)
            return 200
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(correct_once), pool.submit(correct_once)]
        assert sorted(f.result(timeout=20) for f in futures) == [200, 412]
    response = client.post(f"/v2/notices/{notice}/jobs", json={"kind": "spec_index", "input_version": 2, "idempotency_key": "test-live-index"})
    assert response.status_code == 202, response.text
    assert run_once(engine, lane="external")
    with engine.begin() as conn:
        job = conn.execute(select(jobs).where(jobs.c.id == response.json()["id"])).mappings().one()
        assert job["status"] == "succeeded", job["error"]
        assert job["result"]["ready_for_evaluation"], job["result"]
        assert conn.execute(select(active_indexes).where(active_indexes.c.notice_no == notice)).first() is None
    result = indexing.search(engine, notice, SearchRequest(requirement_id="req", query="장치 지연"), generation_id=job["result"]["generation"])
    assert not result["degraded"], result["reasons"]
    assert any(r["document_id"] == "good" and r["compliance"] == "meets" for r in result["groups"]["verified"])
    assert any(r["document_id"] == "bad" and r["compliance"] == "does_not_meet" for r in result["groups"]["conflicts"])
    assert all(set(r["ranks"]) == {"lexical", "graph", "dense"} for r in result["groups"]["verified"])
    assert client.get(f"/v2/notices/{notice}/workspace").json()["decision"] == "pending"
    engine.dispose()
