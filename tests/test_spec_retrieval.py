"""Offline retrieval contracts: no database, network, model downloads, or LLMs."""

from __future__ import annotations

import builtins
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql

from api.specifications.retrieval import (
    BGE_M3_MODEL,
    DENSE_DIMENSIONS,
    LEXICAL_SQL,
    NEO4J_COUNT,
    NEO4J_READ,
    NEO4J_UPSERT,
    BgeM3Embedder,
    EvidenceHit,
    GraphEvidence,
    Neo4jEvidenceAdapter,
    QdrantEvidenceAdapter,
    TextEvidence,
    VectorEvidence,
    build_lexical_query,
    exact_identifier,
    reciprocal_rank_fusion,
)

REVISION = "a" * 40
VECTOR = (1.0,) + (0.0,) * (DENSE_DIMENSIONS - 1)


def hit(evidence_id: str, group: str = "trusted") -> EvidenceHit:
    return EvidenceHit(evidence_id=evidence_id, group=group)


def test_rrf_one_based_equal_weights_and_id_ties() -> None:
    result = reciprocal_rank_fusion(
        [hit("b"), hit("a")],
        [hit("a"), hit("b")],
        [hit("c")],
    )
    assert [row.evidence_id for row in result.trusted] == ["a", "b", "c"]
    a, b, c = result.trusted
    assert a.score == b.score == float(Fraction(1, 61) + Fraction(1, 62))
    assert c.score == 1 / 61
    assert a.ranks == {"lexical": 2, "vector": 1}
    assert c.ranks == {"graph": 1}


def test_rrf_all_three_sources_contribute_once() -> None:
    result = reciprocal_rank_fusion([hit("a")] * 3, [hit("a")] * 2, [hit("a")])
    assert len(result.trusted) == 1
    assert result.trusted[0].score == float(Fraction(3, 61))
    assert result.trusted[0].ranks == {"lexical": 1, "vector": 1, "graph": 1}


def test_rrf_dedup_keeps_original_positions_and_caps_before_dedup() -> None:
    result = reciprocal_rank_fusion([hit("a"), hit("a"), hit("b")] + [hit("a")] * 97 + [hit("c")])
    assert [row.evidence_id for row in result.trusted] == ["a", "b"]
    assert result.trusted[1].ranks == {"lexical": 3}
    assert result.trusted[1].score == 1 / 63


@pytest.mark.parametrize("source", ["lexical", "vector", "graph"])
def test_rrf_consumes_at_most_100_positions(source: str) -> None:
    def rows():
        for index in range(100):
            yield hit(str(index))
        pytest.fail("source read beyond 100")

    result = reciprocal_rank_fusion(**{source: rows()})
    assert len(result.trusted) == 100
    assert result.trusted[-1].score == 1 / 160


def test_rrf_groups_have_no_trust_boost_and_no_cross_group_limit() -> None:
    result = reciprocal_rank_fusion([hit("t")], [hit("r", "reference")], [hit("c", "conflicts")])
    assert result.trusted[0].score == result.reference[0].score == result.conflicts[0].score
    assert result.reference[0].group == "reference"
    assert reciprocal_rank_fusion().model_dump() == {
        "trusted": (),
        "reference": (),
        "conflicts": (),
    }


def test_rrf_disagreeing_annotations_are_conflicts_independent_of_source() -> None:
    first = reciprocal_rank_fusion([hit("a")], [hit("a", "reference")])
    second = reciprocal_rank_fusion([hit("a", "reference")], [hit("a")])
    assert first == second
    assert not first.trusted and not first.reference
    assert first.conflicts[0].score == float(Fraction(2, 61))


@pytest.mark.parametrize(
    "value, expected",
    [
        ("  CAN2.0B\t", "can2.0b"),
        ("CAN2.0A", "can2.0a"),
        ("PLECS  4.9.1", "plecs 4.9.1"),
        ("IEC-61850/8-1:2011", "iec-61850/8-1:2011"),
        ("ABB_5SNA-1200E330100", "abb_5sna-1200e330100"),
        ("C++", "c++"),
        ("v01.02", "v01.02"),
        ("", ""),
    ],
)
def test_exact_identifier(value: str, expected: str) -> None:
    assert exact_identifier(value) == expected
    assert exact_identifier(expected) == expected


@pytest.mark.parametrize(
    "left, right",
    [
        ("CAN2.0B", "CAN2.0A"),
        ("CAN2.0B", "CAN20B"),
        ("X-1", "X1"),
        ("C++", "C"),
        ("v1.10", "v1.1"),
        ("AB/12", "AB-12"),
        ("x\u00b2", "x2"),
    ],
)
def test_identifiers_do_not_collapse_protocols_models_versions(left: str, right: str) -> None:
    assert exact_identifier(left) != exact_identifier(right)


def test_identifier_canonical_unicode_only() -> None:
    assert exact_identifier("e\u0301") == exact_identifier("\u00e9")


def test_lexical_builder_binds_injection_text_and_exact_array() -> None:
    attack = "'); DROP TABLE spec_evidence; --"
    statement = build_lexical_query(
        attack, generation_id=attack, identifiers=[attack, "CAN2.0B", " can2.0b ", ""], limit=999
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    assert attack not in str(compiled)
    assert compiled.params == {
        "query_text": attack,
        "generation_id": attack,
        "identifiers": sorted([exact_identifier(attack), "can2.0b"]),
        "limit": 100,
    }
    assert "ts_rank_cd" in str(compiled)
    assert "plainto_tsquery('simple'" in str(compiled)
    assert "CAST(" in str(compiled) and "TEXT[]" in str(compiled)
    assert "e.generation_id =" in str(compiled)
    assert "e.id ASC" in str(compiled)
    assert "FROM spec_search_chunks" in str(compiled)
    assert "to_tsvector('simple', COALESCE(e.payload->>'search_text', e.quote))" in str(compiled)
    assert "CAST(e.identifiers AS JSONB) ? wanted.identifier" in str(compiled)
    assert "SELECT count(*) FROM unnest" in str(compiled)
    assert "ORDER BY exact_matches DESC, lexical_score DESC" in str(compiled)
    assert "e.id AS evidence_id" in str(compiled)
    assert statement.text == LEXICAL_SQL


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_lexical_invalid_limits_fail_closed(limit: int) -> None:
    with pytest.raises(ValueError):
        build_lexical_query("query", generation_id="g", limit=limit)


def test_blank_generation_rejected() -> None:
    with pytest.raises(ValueError):
        build_lexical_query("query", generation_id=" ")


class FakeGraph:
    def __init__(self) -> None:
        self.calls = []
        self.rows = [{"evidence_id": "a", "group": "reference", "generation_id": "g"}]

    def session(self, **kwargs):
        self.database = kwargs["database"]
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute_read(self, fn):
        return fn(self)

    def execute_write(self, fn):
        return fn(self)

    def run(self, query, **params):
        self.calls.append((query, params))
        if query == NEO4J_READ:
            return self.rows
        if query == NEO4J_COUNT:
            return SimpleNamespace(single=lambda: {"count": len(self.rows)})
        assert query == NEO4J_UPSERT
        return SimpleNamespace(single=lambda: {"count": len(params["rows"])})


def test_neo4j_uses_fixed_bound_queries_and_generation() -> None:
    driver = FakeGraph()
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    attack = "x'}) DETACH DELETE e //"
    assert adapter.read([attack, "CAN2.0B"], limit=1000) == (hit("a", "reference"),)
    query, params = driver.calls[-1]
    assert query == NEO4J_READ and attack not in query
    assert params == {
        "generation_id": "g",
        "identifiers": sorted([exact_identifier(attack), "can2.0b"]),
        "properties": [],
        "limit": 100,
    }
    assert driver.database == "specs"
    assert (
        adapter.upsert(
            [
                GraphEvidence(
                    evidence_id=attack,
                    group="reference",
                    document_id="doc1",
                    exact_identifiers=("CAN2.0B", "can2.0b"),
                    properties=("Voltage",),
                )
            ]
        )
        == 1
    )
    query, params = driver.calls[-1]
    assert query == NEO4J_UPSERT and attack not in query
    assert params["generation_id"] == "g"
    assert params["rows"][0]["exact_identifiers"] == ["can2.0b"]
    assert params["rows"][0]["properties"] == ["voltage"]
    assert params["rows"][0]["document_id"] == "doc1"
    assert "generation_id: $generation_id, evidence_id: row.evidence_id" in query
    assert "MERGE (d)-[:HAS_EVIDENCE]->(e)" in query
    assert "MERGE (e)-[:HAS_PROPERTY]->(p)" in query
    assert "DELETE old_link" in query


def test_neo4j_empty_inputs_and_duplicates() -> None:
    driver = FakeGraph()
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    assert adapter.read([]) == () and adapter.upsert([]) == 0
    row = GraphEvidence(evidence_id="a", group="trusted", document_id="doc1")
    with pytest.raises(ValueError, match="duplicate"):
        adapter.upsert([row, row])
    assert driver.calls == []


def test_neo4j_bad_provenance_or_backend_error_is_not_empty_success() -> None:
    driver = FakeGraph()
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    driver.rows[0]["generation_id"] = "old"
    with pytest.raises(ValueError, match="generation"):
        adapter.read(["CAN2.0B"])
    driver.run = Mock(side_effect=RuntimeError("unavailable"))
    with pytest.raises(RuntimeError, match="unavailable"):
        adapter.read(["CAN2.0B"])


def test_neo4j_property_only_query_bounded_hops_and_count() -> None:
    driver = FakeGraph()
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    assert adapter.read(properties=[" Voltage ", "voltage"]) == (hit("a", "reference"),)
    query, params = driver.calls[-1]
    assert params["identifiers"] == [] and params["properties"] == ["voltage"]
    assert "identifier_matches + property_matches AS matches" in query
    assert "THEN 1 ELSE 2 END AS shortest_hop" in query
    assert "ORDER BY matches DESC, shortest_hop ASC, evidence_id ASC" in query
    assert query.count("generation_id: $generation_id") == 3
    assert "*" not in query
    assert adapter.count() == 1
    assert driver.calls[-1] == (NEO4J_COUNT, {"generation_id": "g"})


def test_neo4j_wrong_upsert_count_raises_inside_write_transaction() -> None:
    driver = FakeGraph()
    driver.run = Mock(return_value=SimpleNamespace(single=lambda: {"count": 0}))
    adapter = Neo4jEvidenceAdapter(driver, database="specs", generation_id="g")
    with pytest.raises(ValueError, match="upsert count"):
        adapter.upsert([GraphEvidence(evidence_id="a", group="reference", document_id="doc1")])


def fake_embedding_model() -> Mock:
    model = Mock()
    model.max_seq_length = 8192
    model.tokenizer.return_value = {"input_ids": [[0, 1, 2]]}
    return model


@pytest.mark.parametrize("revision", ["", "main", "latest", "v1.0", "abc123", "A" * 40])
def test_mutable_or_missing_revision_rejected(tmp_path, revision: str) -> None:
    with pytest.raises(ValueError, match="revision"):
        BgeM3Embedder(snapshot_path=tmp_path, revision=revision)
    with pytest.raises(ValueError, match="revision"):
        QdrantEvidenceAdapter(Mock(), generation_id="g", revision=revision)


def test_bge_requires_explicit_load_and_existing_pinned_snapshot(tmp_path) -> None:
    factory = Mock()
    embedder = BgeM3Embedder(
        snapshot_path=tmp_path / "missing", revision=REVISION, model_factory=factory
    )
    with pytest.raises(RuntimeError, match="not loaded"):
        embedder.embed(["CAN2.0B"])
    with pytest.raises(FileNotFoundError):
        embedder.load_local()
    factory.assert_not_called()
    embedder = BgeM3Embedder(snapshot_path=tmp_path, revision=REVISION, model_factory=factory)
    with pytest.raises(ValueError, match="snapshot"):
        embedder.load_local()
    factory.assert_not_called()


def test_bge_local_only_factory_and_dense_output(tmp_path) -> None:
    snapshot = tmp_path / "snapshots" / REVISION
    snapshot.mkdir(parents=True)
    model = fake_embedding_model()
    model.get_sentence_embedding_dimension.return_value = 1024
    model.encode.return_value = [VECTOR]
    factory = Mock(return_value=model)
    embedder = BgeM3Embedder(snapshot_path=snapshot, revision=REVISION, model_factory=factory)
    embedder.load_local()
    embedder.load_local()
    factory.assert_called_once_with(
        str(snapshot.resolve()),
        revision=REVISION,
        local_files_only=True,
        trust_remote_code=False,
        model_kwargs={"weights_only": True},
        device="cpu",
    )
    assert embedder.revision == REVISION
    assert embedder.embed(["CAN2.0B"]) == (VECTOR,)
    model.encode.assert_called_once_with(
        ["CAN2.0B"],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
        prompt="",
    )
    assert embedder.embed([]) == ()


@pytest.mark.parametrize("output", [[(1.0,)], [tuple([float("nan")] * 1024)], [(0.0,) * 1024], []])
def test_bge_rejects_invalid_outputs(tmp_path, output) -> None:
    snapshot = tmp_path / "snapshots" / REVISION
    snapshot.mkdir(parents=True)
    model = fake_embedding_model()
    model.get_sentence_embedding_dimension.return_value = 1024
    model.encode.return_value = output
    embedder = BgeM3Embedder(
        snapshot_path=snapshot, revision=REVISION, model_factory=Mock(return_value=model)
    )
    embedder.load_local()
    with pytest.raises(ValueError):
        embedder.embed(["query"])


def test_failed_load_does_not_mark_bge_ready(tmp_path) -> None:
    snapshot = tmp_path / "snapshots" / REVISION
    snapshot.mkdir(parents=True)
    model = fake_embedding_model()
    model.get_sentence_embedding_dimension.return_value = 768
    embedder = BgeM3Embedder(
        snapshot_path=snapshot, revision=REVISION, model_factory=Mock(return_value=model)
    )
    with pytest.raises(ValueError, match="1024"):
        embedder.load_local()
    with pytest.raises(RuntimeError, match="not loaded"):
        embedder.embed(["query"])


@pytest.mark.parametrize("max_length, accepted", [(2, False), (3, True)])
def test_bge_checks_full_token_length_including_special_tokens(
    tmp_path, max_length, accepted
) -> None:
    snapshot = tmp_path / "snapshots" / REVISION
    snapshot.mkdir(parents=True)
    model = fake_embedding_model()
    model.get_sentence_embedding_dimension.return_value = 1024
    model.max_seq_length = max_length
    model.encode.return_value = [VECTOR]
    embedder = BgeM3Embedder(
        snapshot_path=snapshot, revision=REVISION, model_factory=Mock(return_value=model)
    )
    embedder.load_local()
    if accepted:
        assert embedder.embed(["query"]) == (VECTOR,)
    else:
        with pytest.raises(ValueError, match="truncation is forbidden"):
            embedder.embed(["query"])
        model.encode.assert_not_called()
    model.tokenizer.assert_called_once_with(
        ["query"],
        add_special_tokens=True,
        truncation=False,
        padding=False,
        return_attention_mask=False,
        return_token_type_ids=False,
    )


def test_bge_overflow_in_later_batch_item_rejects_entire_batch(tmp_path) -> None:
    snapshot = tmp_path / "snapshots" / REVISION
    snapshot.mkdir(parents=True)
    model = fake_embedding_model()
    model.get_sentence_embedding_dimension.return_value = 1024
    model.max_seq_length = 3
    model.tokenizer.return_value = {"input_ids": [[0, 1], [0, 1, 2, 3]]}
    embedder = BgeM3Embedder(
        snapshot_path=snapshot, revision=REVISION, model_factory=Mock(return_value=model)
    )
    embedder.load_local()
    with pytest.raises(ValueError, match="truncation is forbidden"):
        embedder.embed(["short", "long"])
    model.encode.assert_not_called()


@pytest.mark.parametrize("max_length", [None, 0, True])
def test_bge_missing_or_invalid_token_limit_fails_closed(tmp_path, max_length) -> None:
    snapshot = tmp_path / "snapshots" / REVISION
    snapshot.mkdir(parents=True)
    model = fake_embedding_model()
    model.get_sentence_embedding_dimension.return_value = 1024
    model.max_seq_length = max_length
    embedder = BgeM3Embedder(
        snapshot_path=snapshot, revision=REVISION, model_factory=Mock(return_value=model)
    )
    embedder.load_local()
    with pytest.raises(ValueError, match="max_seq_length"):
        embedder.embed(["query"])
    model.encode.assert_not_called()


FAKE_MODELS = SimpleNamespace(
    Distance=SimpleNamespace(COSINE="Cosine"),
    VectorParams=SimpleNamespace,
    PointStruct=SimpleNamespace,
)


class FakeQdrant:
    def __init__(self) -> None:
        self.collections = {}
        self.points = []
        self.calls = []

    def collection_exists(self, name):
        return name in self.collections

    def create_collection(self, *, collection_name, vectors_config):
        self.calls.append(("create", collection_name))
        self.collections[collection_name] = vectors_config

    def get_collection(self, name):
        return SimpleNamespace(
            config=SimpleNamespace(params=SimpleNamespace(vectors=self.collections[name]))
        )

    def upsert(self, **kwargs):
        self.calls.append(("upsert", kwargs))
        self.points = kwargs["points"]

    def query_points(self, **kwargs):
        self.calls.append(("query", kwargs))
        return SimpleNamespace(
            points=[SimpleNamespace(payload=p.payload, score=0.5) for p in self.points]
        )

    def count(self, **kwargs):
        self.calls.append(("count", kwargs))
        return SimpleNamespace(count=len(self.points))


def vector_adapter(client, generation="g", revision=REVISION) -> QdrantEvidenceAdapter:
    return QdrantEvidenceAdapter(
        client, generation_id=generation, revision=revision, models=FAKE_MODELS
    )


def test_qdrant_dedicated_generation_revision_collections_and_cosine() -> None:
    client = FakeQdrant()
    client.collections["existing_sku"] = "untouched"
    adapter = vector_adapter(client)
    assert adapter.collection_name.startswith("specifications_bge_m3_")
    assert adapter.collection_name == vector_adapter(client).collection_name
    assert adapter.collection_name != vector_adapter(client, "g2").collection_name
    assert adapter.collection_name != vector_adapter(client, revision="b" * 40).collection_name
    assert client.calls == []
    adapter.ensure_collection()
    adapter.ensure_collection()
    assert len(client.calls) == 1
    assert client.collections[adapter.collection_name].size == 1024
    assert client.collections[adapter.collection_name].distance == "Cosine"
    assert client.collections["existing_sku"] == "untouched"


def test_qdrant_upsert_stable_ids_raw_dense_query_and_tie_id() -> None:
    client = FakeQdrant()
    adapter = vector_adapter(client)
    adapter.ensure_collection()
    rows = [
        VectorEvidence(evidence_id=name, group="reference", vector=VECTOR) for name in ["b", "a"]
    ]
    adapter.upsert(rows)
    first_id = client.points[0].id
    adapter.upsert(rows)
    assert client.points[0].id == first_id
    assert client.points[0].payload == {
        "evidence_id": "b",
        "group": "reference",
        "generation_id": "g",
        "model_id": BGE_M3_MODEL,
        "model_revision": REVISION,
    }
    assert client.calls[-1][1]["wait"] is True
    assert adapter.search(VECTOR, limit=500) == (hit("a", "reference"), hit("b", "reference"))
    assert client.calls[-1][1] == {
        "collection_name": adapter.collection_name,
        "query": list(VECTOR),
        "limit": 100,
        "with_payload": True,
        "with_vectors": False,
    }


@pytest.mark.parametrize(
    "vectors",
    [
        SimpleNamespace(size=768, distance="Cosine"),
        SimpleNamespace(size=1024, distance="Dot"),
        {"dense": SimpleNamespace(size=1024, distance="Cosine")},
    ],
)
def test_qdrant_incompatible_collection_fails_without_repair(vectors) -> None:
    client = FakeQdrant()
    adapter = vector_adapter(client)
    client.collections[adapter.collection_name] = vectors
    with pytest.raises(ValueError, match="dense1024 cosine"):
        adapter.ensure_collection()
    with pytest.raises(ValueError):
        adapter.search(VECTOR)
    with pytest.raises(ValueError):
        adapter.upsert([VectorEvidence(evidence_id="a", group="trusted", vector=VECTOR)])
    assert client.calls == []


def test_qdrant_query_does_not_create_missing_collection() -> None:
    client = FakeQdrant()
    with pytest.raises(KeyError):
        vector_adapter(client).search(VECTOR)
    assert client.calls == []


def test_qdrant_exact_count_is_generation_scoped_without_provisioning() -> None:
    client = FakeQdrant()
    adapter = vector_adapter(client)
    with pytest.raises(KeyError):
        adapter.count()
    assert client.calls == []
    adapter.ensure_collection()
    adapter.upsert([VectorEvidence(evidence_id="a", group="reference", vector=VECTOR)])
    assert adapter.count() == 1
    assert client.calls[-1] == (
        "count",
        {"collection_name": adapter.collection_name, "exact": True},
    )


@pytest.mark.parametrize(
    "key, value", [("generation_id", "old"), ("model_revision", "b" * 40), ("model_id", "other")]
)
def test_qdrant_mismatched_provenance_fails_closed(key, value) -> None:
    client = FakeQdrant()
    adapter = vector_adapter(client)
    adapter.ensure_collection()
    adapter.upsert([VectorEvidence(evidence_id="a", group="trusted", vector=VECTOR)])
    client.points[0].payload[key] = value
    with pytest.raises(ValueError, match="provenance"):
        adapter.search(VECTOR)


@pytest.mark.parametrize("vector", [(1.0,), (0.0,) * 1024, (float("inf"),) * 1024])
def test_qdrant_invalid_dense_values_fail_before_client_calls(vector) -> None:
    client = FakeQdrant()
    with pytest.raises(ValueError):
        vector_adapter(client).search(vector)
    with pytest.raises(ValueError):
        VectorEvidence(evidence_id="a", group="trusted", vector=vector)
    assert client.calls == []


def test_qdrant_no_duplicate_upserts_or_empty_writes() -> None:
    client = FakeQdrant()
    adapter = vector_adapter(client)
    adapter.upsert([])
    row = VectorEvidence(evidence_id="a", group="trusted", vector=VECTOR)
    with pytest.raises(ValueError, match="duplicate"):
        adapter.upsert([row, row])
    assert client.calls == []


def test_qdrant_index_and_query_use_explicitly_loaded_local_model(tmp_path) -> None:
    snapshot = tmp_path / "snapshots" / REVISION
    snapshot.mkdir(parents=True)
    model = fake_embedding_model()
    model.get_sentence_embedding_dimension.return_value = 1024
    model.encode.return_value = [VECTOR]
    factory = Mock(return_value=model)
    embedder = BgeM3Embedder(snapshot_path=snapshot, revision=REVISION, model_factory=factory)
    client = FakeQdrant()
    adapter = vector_adapter(client)
    row = TextEvidence(evidence_id="a", group="reference", text="CAN2.0B")
    with pytest.raises(RuntimeError, match="not loaded"):
        adapter.query("CAN2.0B", embedder=embedder)
    with pytest.raises(RuntimeError, match="not loaded"):
        adapter.index([row], embedder=embedder)
    assert client.calls == []
    factory.assert_not_called()
    embedder.load_local()
    assert adapter.index([row], embedder=embedder) == 1
    assert adapter.query("CAN2.0B", embedder=embedder) == (hit("a", "reference"),)
    factory.assert_called_once()


def test_qdrant_text_methods_reject_revision_mismatch_before_embedding(tmp_path) -> None:
    client = FakeQdrant()
    embedder = BgeM3Embedder(snapshot_path=tmp_path, revision="b" * 40)
    adapter = vector_adapter(client)
    with pytest.raises(ValueError, match="revision"):
        adapter.query("CAN2.0B", embedder=embedder)
    with pytest.raises(ValueError, match="revision"):
        adapter.index([], embedder=embedder)
    assert client.calls == []


def test_import_does_not_import_optional_sdks(monkeypatch) -> None:
    import importlib.util

    import api.specifications.retrieval as retrieval

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name.split(".")[0] not in {
            "neo4j",
            "qdrant_client",
            "sentence_transformers",
            "transformers",
            "torch",
            "FlagEmbedding",
        }
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    spec = importlib.util.spec_from_file_location(
        "retrieval_without_optional_sdks", retrieval.__file__
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.exact_identifier("CAN2.0B") == "can2.0b"
