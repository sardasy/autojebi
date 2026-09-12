"""Fixed graph-write and explicit schema contracts, using no external connections."""

import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from api.specifications.retrieval import (
    NEO4J_SCHEMA_STATEMENTS,
    NEO4J_UPSERT,
    NEO4J_UPSERT_REQUIREMENTS,
    GraphEvidence,
    GraphRequirement,
    Neo4jEvidenceAdapter,
    ensure_graph_schema,
)


class FakeDriver:
    def __init__(self):
        self.calls = []
        self.databases = []
        self.count_override = None
        self.consumed = 0
        self.rollback = False

    def session(self, *, database):
        self.databases.append(database)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute_write(self, callback):
        try:
            return callback(self)
        except Exception:
            self.rollback = True
            raise

    def run(self, statement, **params):
        self.calls.append((statement, params))
        count = (
            self.count_override if self.count_override is not None else len(params.get("rows", []))
        )
        return SimpleNamespace(single=lambda: {"count": count}, consume=self.consume)

    def consume(self):
        self.consumed += 1


def requirement(**changes):
    return GraphRequirement(
        **{
            "requirement_id": "req1",
            "notice_no": "notice1",
            "document_id": "doc1",
            "property": "latency",
            "target": "Device-1.0",
            "source_sha256": "a" * 64,
            **changes,
        }
    )


def test_evidence_targets_default_and_canonical_product_relationship():
    driver = FakeDriver()
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="generation1")
    default = GraphEvidence(evidence_id="e0", group="reference", document_id="doc1")
    assert default.targets == ()
    row = GraphEvidence(
        evidence_id="e1",
        group="reference",
        document_id="doc1",
        targets=(" Device-1.0 ", "device-1.0", "Device-1.1"),
    )
    assert row.targets == ("device-1.0", "device-1.1")
    assert adapter.upsert([row]) == 1
    query, params = driver.calls[0]
    assert query == NEO4J_UPSERT
    assert params["generation_id"] == "generation1"
    assert params["rows"][0]["targets"] == ["device-1.0", "device-1.1"]
    assert "SpecProduct {generation_id: $generation_id, value: target}" in query
    assert "MERGE (e)-[:ABOUT]->(product)" in query
    assert "WHERE NOT old_product.value IN row.targets" in query


def test_requirement_relationships_are_fixed_parameterized_and_generation_scoped():
    driver = FakeDriver()
    attack = "x'}) DETACH DELETE n //"
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id=attack)
    row = requirement(requirement_id=attack, property=" LATENCY ", target=" Device-1.0 ")
    assert adapter.upsert_requirements([row]) == 1
    query, params = driver.calls[0]
    assert query == NEO4J_UPSERT_REQUIREMENTS and attack not in query
    assert params == {"generation_id": attack, "rows": [row.model_dump(mode="json")]}
    assert params["rows"][0]["property"] == "latency"
    assert params["rows"][0]["target"] == "device-1.0"
    for relation in (
        "(n)-[:REQUIRES]->(r)",
        "(r)-[:REQUIRES_PROPERTY]->(p)",
        "(r)-[:ABOUT]->(product)",
        "(r)-[:SOURCED_FROM]->(d)",
    ):
        assert f"MERGE {relation}" in query
    assert query.count("generation_id: $generation_id") == 6
    assert "WHERE d.source_sha256 IS NULL OR d.source_sha256 = row.source_sha256" in query
    assert "SET r.source_sha256 = row.source_sha256" in query
    assert "DELETE old_link" in query
    assert driver.databases == ["specs"]


@pytest.mark.parametrize(
    "changes",
    [
        {"requirement_id": " "},
        {"requirement_id": "x" * 101},
        {"notice_no": ""},
        {"notice_no": "x" * 101},
        {"document_id": "x" * 201},
        {"property": " "},
        {"property": "x" * 101},
        {"target": "x" * 201},
        {"source_sha256": "latest"},
        {"source_sha256": "A" * 64},
        {"body": "RETURN 1"},
    ],
)
def test_requirement_schema_rejects_unbounded_or_arbitrary_body(changes):
    with pytest.raises(ValidationError):
        requirement(**changes)


def test_validation_finishes_before_opening_write_session():
    driver = FakeDriver()
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    invalid = requirement().model_copy(update={"source_sha256": "invalid"})
    with pytest.raises(ValidationError):
        adapter.upsert_requirements([requirement(), invalid])
    assert driver.calls == driver.databases == []


@pytest.mark.parametrize("targets", [(" ",), ("x" * 201,), tuple(str(i) for i in range(101))])
def test_product_targets_are_bounded(targets):
    with pytest.raises(ValidationError):
        GraphEvidence(evidence_id="e", group="reference", document_id="d", targets=targets)


def test_requirement_duplicates_and_source_hash_conflicts_fail_before_write():
    driver = FakeDriver()
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    with pytest.raises(ValueError, match="duplicate"):
        adapter.upsert_requirements([requirement(), requirement()])
    with pytest.raises(ValueError, match="source hashes"):
        adapter.upsert_requirements(
            [requirement(), requirement(requirement_id="req2", source_sha256="b" * 64)]
        )
    assert driver.calls == driver.databases == []
    assert adapter.upsert_requirements([requirement(), requirement(notice_no="notice2")]) == 2


@pytest.mark.parametrize("method", ["upsert", "upsert_requirements"])
def test_graph_batch_cap_and_empty_batches(method):
    driver = FakeDriver()
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    call = getattr(adapter, method)
    assert call([]) == 0
    row = (
        requirement()
        if method == "upsert_requirements"
        else GraphEvidence(evidence_id="e", group="reference", document_id="d")
    )
    with pytest.raises(ValueError, match="3000"):
        call([row] * 3001)
    assert driver.calls == driver.databases == []


def test_exactly_3000_requirements_are_allowed():
    driver = FakeDriver()
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    assert (
        adapter.upsert_requirements([requirement(requirement_id=str(i)) for i in range(3000)])
        == 3000
    )
    assert len(driver.calls) == 1


def test_short_write_or_stored_source_mismatch_rolls_back():
    driver = FakeDriver()
    driver.count_override = 0
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    with pytest.raises(ValueError, match="count/source hash mismatch"):
        adapter.upsert_requirements([requirement()])
    assert driver.rollback


def test_schema_provisioning_is_explicit_fixed_and_idempotent():
    driver = FakeDriver()
    Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    assert not driver.calls and not driver.databases
    ensure_graph_schema(driver, "specs")
    assert driver.calls == [(statement, {}) for statement in NEO4J_SCHEMA_STATEMENTS]
    assert len(driver.calls) == driver.consumed == 6
    assert all("IF NOT EXISTS" in query and "n.generation_id" in query for query, _ in driver.calls)
    assert any("n.notice_no, n.requirement_id" in query for query, _ in driver.calls)
    assert driver.databases == ["specs"]


def test_schema_provisioning_does_not_swallow_errors():
    driver = FakeDriver()

    def unavailable(*args, **kwargs):
        raise RuntimeError("unavailable")

    driver.run = unavailable
    with pytest.raises(RuntimeError, match="unavailable"):
        ensure_graph_schema(driver, "specs")
    with pytest.raises(ValueError, match="database"):
        ensure_graph_schema(driver, " ")


def test_graph_schema_cli_uses_explicit_provisioning(monkeypatch, capsys):
    from api.specifications import indexing
    from api.specifications.__main__ import main

    provision = Mock()
    monkeypatch.setattr(indexing, "provision_graph_schema", provision)
    monkeypatch.setattr(sys, "argv", ["specifications", "graph-schema"])
    main()
    provision.assert_called_once_with()
    assert "constraints provisioned" in capsys.readouterr().out


def test_provisioning_requires_validation_environment(monkeypatch):
    from fastapi import HTTPException

    from api.specifications import indexing

    driver = FakeDriver()

    @contextmanager
    def configured_driver():
        yield driver

    monkeypatch.setattr(indexing, "graph_driver", configured_driver)
    monkeypatch.setenv("SPEC_SEARCH_ENABLED", "true")
    monkeypatch.setenv("SPEC_SEARCH_ENV", "production")
    with pytest.raises(HTTPException):
        indexing.provision_graph_schema()
    assert driver.calls == []
    monkeypatch.setenv("SPEC_SEARCH_ENV", "validation")
    indexing.provision_graph_schema()
    assert driver.calls == [(statement, {}) for statement in NEO4J_SCHEMA_STATEMENTS]
