"""Offline safety regressions using real source bytes only under pytest's tmp_path."""

from __future__ import annotations

import copy
import hashlib
from contextlib import contextmanager
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from api.main import app  # noqa: F401
from api.specifications import indexing
from api.specifications.models import SearchRequest, Specification
from api.specifications.retrieval import EvidenceHit
from api.specifications.tables import active_indexes, chunks, generations
from api.specifications.validation import sha, validate_spec
from api.workspace import asset_policy
from api.workspace import service as workspace
from api.workspace.tables import jobs, workspaces

NOTICE = "SPEC-INDEX-SAFETY-TEST"
TODAY = date(2026, 9, 11)


def source_document(root: Path, doc_id: str, text: str, role: str) -> dict:
    path = root / f"{doc_id}.txt"
    path.write_text(text, encoding="utf-8")
    return {
        "id": doc_id,
        "name": path.name,
        "role": role,
        "text": text,
        "storage_path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "confirmed": role != "notice_source",
        "text_origin": "manual_confirmed",
    }


@pytest.fixture
def safety_index(client, sqlite_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("SPEC_SEARCH_ENABLED", "true")
    monkeypatch.setenv("SPEC_SEARCH_ENV", "validation")
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    clock = [TODAY]
    monkeypatch.setattr(asset_policy, "today", lambda: clock[0])
    response = client.post(
        "/v2/notices", json={"notice_no": NOTICE, "title": "TEST ONLY", "source": "TEST"}
    )
    assert response.is_success, response.text
    response = client.post(f"/v2/notices/{NOTICE}/initialize")
    assert response.is_success, response.text

    raw = "Device latency 1ms \uc774\ud558"
    source = source_document(tmp_path, "notice", raw, "notice_source")
    requirement = Specification(
        target="Device",
        property="latency",
        kind="numeric",
        operator="le",
        value="1",
        unit="ms",
        raw=raw,
        source={
            "document_id": source["id"],
            "document_sha256": source["sha256"],
            "text_sha256": sha(raw),
            "start": 0,
            "end": len(raw),
            "quote": raw,
            "locator": "line 1",
        },
    )
    validation = validate_spec(requirement, source)
    assert validation["status"] == "valid", validation
    trusted = source_document(tmp_path, "trusted", "Device latency 0.5ms", "product_evidence")
    trusted["company_asset"] = {"active": True, "expires_on": TODAY.isoformat()}
    reference = source_document(tmp_path, "reference", "Device latency 0.5ms", "company_reference")
    conflict = source_document(tmp_path, "conflict", "Device latency 2ms", "product_evidence")
    with sqlite_engine.begin() as conn:
        ws = workspace.load(conn, NOTICE)
        inputs = copy.deepcopy(ws["inputs"])
        inputs["documents"] = [source, trusted, reference, conflict]
        inputs["specifications"] = {
            "req": {"payload": requirement.model_dump(mode="json"), "validation": validation}
        }
        conn.execute(
            update(workspaces).where(workspaces.c.notice_no == NOTICE).values(inputs=inputs)
        )
        job = workspace.create_job_record(
            conn, {**ws, "inputs": inputs}, "spec_index", "TEST-safety-index", {}
        )
        conn.execute(update(jobs).where(jobs.c.id == job["id"]).values(status="succeeded"))
        rows = indexing.make_chunks(inputs)
        assert len(rows) == 3
        assert all(row["payload"]["observations"] for row in rows)
        # Stale external/index trust annotations must not promote company_reference.
        for row in rows:
            row["payload"]["group"] = "trusted"
        gid = workspace.uid()
        manifest = {"snapshot_path": "FAKE-NOT-LOADED", "revision": "a" * 40}
        conn.execute(
            generations.insert().values(
                id=gid,
                notice_no=NOTICE,
                job_id=job["id"],
                input_version=ws["version"],
                input_hash=workspace.digest(inputs),
                manifest=manifest,
                stores={},
                status="ready",
                created_at=workspace.now(),
            )
        )
        conn.execute(chunks.insert(), [{**row, "generation_id": gid} for row in rows])
        conn.execute(active_indexes.insert().values(notice_no=NOTICE, generation_id=gid))

    lexical_ids = sorted(row["id"] for row in rows)
    fake = SimpleNamespace(
        calls=[],
        on_dense=None,
        dense=lexical_ids[1:] + lexical_ids[:1],
        graph=lexical_ids[2:] + lexical_ids[:2],
    )

    def graph_read(*args, **kwargs):
        fake.calls.append("graph")
        return [EvidenceHit(evidence_id=key, group="trusted") for key in fake.graph]

    def dense_search(*args, **kwargs):
        fake.calls.append("dense")
        if fake.on_dense is not None:
            fake.on_dense()
        return [EvidenceHit(evidence_id=key, group="trusted") for key in fake.dense]

    @contextmanager
    def graph_adapter(generation_id):
        assert generation_id == gid
        yield SimpleNamespace(read=graph_read)

    @contextmanager
    def vector_adapter(generation_id, actual_manifest):
        assert generation_id == gid and actual_manifest == manifest
        yield SimpleNamespace(search=dense_search)

    def embed(texts):
        fake.calls.append("embed")
        return [(1.0,) + (0.0,) * 1023 for _ in texts]

    monkeypatch.setattr(indexing, "graph_adapter", graph_adapter)
    monkeypatch.setattr(indexing, "vector_adapter", vector_adapter)
    monkeypatch.setattr(indexing, "embedder", lambda *args: SimpleNamespace(embed=embed))
    return SimpleNamespace(
        engine=sqlite_engine,
        inputs=inputs,
        source=source,
        generation=gid,
        version=ws["version"],
        clock=clock,
        fake=fake,
        rows=rows,
        lexical_ids=lexical_ids,
        ids={row["document_id"]: row["id"] for row in rows},
    )


def search(seed) -> dict:
    return indexing.search(
        seed.engine, NOTICE, SearchRequest(query="Device latency", requirement_id="req")
    )


def bump_only_version(seed) -> None:
    with seed.engine.begin() as conn:
        conn.execute(
            update(workspaces)
            .where(workspaces.c.notice_no == NOTICE)
            .values(
                version=workspaces.c.version + 1,
            )
        )
        ws = workspace.load(conn, NOTICE)
        generation = (
            conn.execute(
                select(generations).where(
                    generations.c.id == seed.generation,
                )
            )
            .mappings()
            .one()
        )
        assert ws["version"] == generation["input_version"] + 1
        assert workspace.digest(ws["inputs"]) == generation["input_hash"]


def test_legacy_confirmation_without_validity_is_reference():
    doc = {"confirmed": True, "role": "product_evidence"}
    assert indexing.group_for(doc, {}) == "reference"
    doc["company_asset"] = {"active": True, "no_expiry": True}
    assert indexing.group_for(doc, {}) == "trusted"
    doc["role"] = "company_reference"
    assert indexing.group_for(doc, {}) == "reference"


@pytest.mark.parametrize("prefix", ["", "Header\n"])
def test_split_assertion_keeps_text_but_emits_no_equality_observations(
    safety_index, tmp_path, prefix
):
    ending = "Device latency 1ms"
    long_line = "x" * (600 - len(ending) - 1) + " " + ending + " \ucd08\uacfc\n"
    text = prefix + long_line + "Device latency 0.5ms\n"
    doc = source_document(tmp_path, "split", text, "product_evidence")
    inputs = copy.deepcopy(safety_index.inputs)
    inputs["documents"] = [safety_index.source, doc]
    rows = indexing.make_chunks(inputs)
    assert "".join(row["quote"] for row in rows) == text
    fragments = [row for row in rows if len(prefix) <= row["start"] < len(prefix) + len(long_line)]
    assert len(fragments) == 2
    assert fragments[0]["quote"].endswith(ending)
    for row in fragments:
        assert row["quote"] == text[row["start"] : row["end"]]
        assert row["document_sha256"] == doc["sha256"]
        assert row["text_sha256"] == sha(text)
        assert row["payload"]["observations"] == []
        assert row["properties"] == []
    # A complete following assertion must still be usable, not globally suppressed.
    observation = rows[-1]["payload"]["observations"][0]
    assert observation["operator"] == "eq" and observation["value"] == "0.5"


@pytest.mark.parametrize("timing", ["before", "during"])
def test_unchanged_hash_does_not_allow_an_old_epoch_search(safety_index, timing):
    seed = safety_index
    baseline = search(seed)
    assert baseline["generation"] == seed.generation
    assert baseline["groups"]["verified"]
    seed.fake.calls.clear()
    if timing == "before":
        bump_only_version(seed)
    else:
        seed.fake.on_dense = lambda: bump_only_version(seed)
    result = search(seed)
    assert result["generation"] is None
    assert result["degraded"] is True and result["reasons"]
    assert result["groups"] == {"verified": [], "references": [], "conflicts": []}
    assert seed.fake.calls == ([] if timing == "before" else ["graph", "embed", "dense"])


def test_three_source_rrf_is_exact_and_revalidates_trust(safety_index):
    seed = safety_index
    result = search(seed)
    assert seed.fake.calls == ["graph", "embed", "dense"]
    assert result["generation"] == seed.generation
    expected = {
        "verified": ("trusted", "meets"),
        "references": ("reference", "unassessed"),
        "conflicts": ("conflict", "does_not_meet"),
    }
    score = float(Fraction(1, 61) + Fraction(1, 62) + Fraction(1, 63))
    for group, (document_id, compliance) in expected.items():
        assert len(result["groups"][group]) == 1
        row = result["groups"][group][0]
        key = seed.ids[document_id]
        assert row["id"] == key and row["compliance"] == compliance
        assert row["rrf"] == score
        assert row["ranks"] == {
            "lexical": seed.lexical_ids.index(key) + 1,
            "dense": seed.fake.dense.index(key) + 1,
            "graph": seed.fake.graph.index(key) + 1,
        }


@pytest.mark.parametrize("timing", ["before", "during"])
def test_expired_trust_is_rechecked_even_when_hash_and_external_hits_are_unchanged(
    safety_index, timing
):
    seed = safety_index
    baseline = search(seed)
    assert baseline["groups"]["verified"][0]["id"] == seed.ids["trusted"]
    assert baseline["groups"]["verified"][0]["compliance"] == "meets"

    def expire():
        seed.clock[0] = TODAY + timedelta(days=1)

    if timing == "before":
        expire()
    else:
        seed.fake.on_dense = expire
    result = search(seed)
    assert result["generation"] == seed.generation
    assert result["groups"]["verified"] == []
    assert seed.ids["trusted"] in seed.fake.dense and seed.ids["trusted"] in seed.fake.graph
    returned = {row["id"] for rows in result["groups"].values() for row in rows}
    assert returned == {seed.ids["reference"], seed.ids["conflict"]}
    assert result["groups"]["references"][0]["compliance"] == "unassessed"
    with seed.engine.begin() as conn:
        ws = workspace.load(conn, NOTICE)
        generation = (
            conn.execute(
                select(generations).where(
                    generations.c.id == seed.generation,
                )
            )
            .mappings()
            .one()
        )
        assert ws["version"] == seed.version == generation["input_version"]
        assert workspace.digest(ws["inputs"]) == generation["input_hash"]


@pytest.mark.parametrize("short_requirement_write", [False, True])
def test_graph_build_maps_requirements_targets_and_checks_counts(
    safety_index, monkeypatch, short_requirement_write
):
    seed = safety_index
    monkeypatch.setenv("SPEC_BGE_REVISION", "a" * 40)
    monkeypatch.setenv("SPEC_BGE_SNAPSHOT", "FAKE-NOT-LOADED")
    recorded = SimpleNamespace(requirements=[], evidence=[], vectors=0, generations=[])

    def upsert_requirements(rows):
        recorded.requirements = rows
        return len(rows) - int(short_requirement_write)

    def upsert_evidence(rows):
        recorded.evidence = rows
        return len(rows)

    def upsert_vectors(rows):
        recorded.vectors += len(rows)

    @contextmanager
    def graph_adapter(gid):
        recorded.generations.append(gid)
        yield SimpleNamespace(
            upsert_requirements=upsert_requirements,
            upsert=upsert_evidence,
            count=lambda: len(recorded.evidence),
        )

    @contextmanager
    def vector_adapter(gid, manifest):
        recorded.generations.append(gid)
        yield SimpleNamespace(
            ensure_collection=lambda: None, upsert=upsert_vectors, count=lambda: recorded.vectors
        )

    def forbidden_schema(*args):
        pytest.fail("build must not automatically provision graph constraints")

    monkeypatch.setattr(indexing, "graph_adapter", graph_adapter)
    monkeypatch.setattr(indexing, "vector_adapter", vector_adapter)
    monkeypatch.setattr(indexing, "ensure_graph_schema", forbidden_schema)
    with seed.engine.begin() as conn:
        ws = workspace.load(conn, NOTICE)
        job = workspace.create_job_record(conn, ws, "spec_index", "TEST-graph-build", {})
        conn.execute(
            update(jobs)
            .where(jobs.c.id == job["id"])
            .values(
                status="running",
                claim_token="TEST-graph-claim",
            )
        )
    result = indexing.build(seed.engine, {**job, "claim_token": "TEST-graph-claim"})
    assert recorded.generations == [result["generation"], result["generation"]]
    assert [row.model_dump() for row in recorded.requirements] == [
        {
            "requirement_id": "req",
            "notice_no": NOTICE,
            "document_id": seed.source["id"],
            "property": "latency",
            "target": "device",
            "source_sha256": seed.source["sha256"],
        }
    ]
    if short_requirement_write:
        assert result["stores"]["graph"]["status"] == "failed"
        assert result["ready_for_evaluation"] is False
        assert recorded.evidence == []
    else:
        assert result["stores"]["graph"]["status"] == "succeeded"
        assert result["ready_for_evaluation"] is True
        assert len(recorded.evidence) == len(seed.rows)
        assert all(row.targets == ("device",) for row in recorded.evidence)
    with seed.engine.begin() as conn:
        generation = (
            conn.execute(
                select(generations).where(
                    generations.c.id == result["generation"],
                )
            )
            .mappings()
            .one()
        )
        manifest = generation["manifest"]
        assert manifest["graph_schema_version"] == indexing.GRAPH_SCHEMA_VERSION
        assert manifest["graph_requirements_hash"] == workspace.digest(
            [row.model_dump(mode="json") for row in recorded.requirements]
        )
        assert (
            conn.execute(
                select(active_indexes.c.generation_id).where(
                    active_indexes.c.notice_no == NOTICE,
                )
            ).scalar_one()
            == seed.generation
        )
