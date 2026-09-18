"""Generation-scoped retrieval, without connections or model loading at import time.

Adapters borrow injected clients; their caller owns transactions/connections and lifecycle.
Nothing here decides whether evidence is trusted. Conflicting group annotations in fusion
are conservatively placed in ``conflicts``. Retrieval never constitutes approval.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
import uuid
from collections.abc import Iterable, Sequence
from fractions import Fraction
from itertools import islice
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Text, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql.elements import TextClause

SOURCE_LIMIT = 100
RRF_K = 60
DENSE_DIMENSIONS = 1024
BGE_M3_MODEL = "BAAI/bge-m3"
EvidenceGroup = Literal["trusted", "reference", "conflicts"]
RetrievalSource = Literal["lexical", "vector", "graph"]


class EvidenceHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(min_length=1)
    group: EvidenceGroup

    @field_validator("evidence_id")
    @classmethod
    def nonblank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence_id must not be blank")
        return value


class FusedHit(EvidenceHit):
    score: float
    ranks: dict[RetrievalSource, int]


class RetrievalGroups(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trusted: tuple[FusedHit, ...] = ()
    reference: tuple[FusedHit, ...] = ()
    conflicts: tuple[FusedHit, ...] = ()


def reciprocal_rank_fusion(
    lexical: Iterable[EvidenceHit] = (),
    vector: Iterable[EvidenceHit] = (),
    graph: Iterable[EvidenceHit] = (),
) -> RetrievalGroups:
    """Fuse three ordered lists with weight=1 and 1/(60 + one-based rank).

    Only the first 100 *positions* per source count. Repeated IDs contribute once,
    at their first position; duplicates neither refill the cap nor compress ranks.
    Grouping happens after scoring, without trust boosts or cross-group truncation.
    Exact rational sums and evidence-ID ties make ordering reproducible.
    """
    ranks: dict[str, dict[RetrievalSource, int]] = {}
    groups: dict[str, set[EvidenceGroup]] = {}
    sources: tuple[tuple[RetrievalSource, Iterable[EvidenceHit]], ...] = (
        ("lexical", lexical),
        ("vector", vector),
        ("graph", graph),
    )
    for source, hits in sources:
        for rank, hit in enumerate(islice(hits, SOURCE_LIMIT), 1):
            ranks.setdefault(hit.evidence_id, {}).setdefault(source, rank)
            groups.setdefault(hit.evidence_id, set()).add(hit.group)
    scores = {
        evidence_id: sum((Fraction(1, RRF_K + rank) for rank in found.values()), Fraction())
        for evidence_id, found in ranks.items()
    }
    buckets: dict[str, list[FusedHit]] = {"trusted": [], "reference": [], "conflicts": []}
    for evidence_id in sorted(ranks, key=lambda key: (-scores[key], key)):
        annotations = groups[evidence_id]
        group: EvidenceGroup = next(iter(annotations)) if len(annotations) == 1 else "conflicts"
        buckets[group].append(
            FusedHit(
                evidence_id=evidence_id,
                group=group,
                score=float(scores[evidence_id]),
                ranks=ranks[evidence_id],
            )
        )
    return RetrievalGroups(**buckets)


def exact_identifier(value: str) -> str:
    """NFC + casefold + normalized whitespace; retain ALL model/version punctuation.

    This normalizes a complete identifier, not free-text token extraction. In particular,
    no compatibility folding, punctuation stripping, or numeric/version coercion occurs.
    """
    return unicodedata.normalize("NFC", " ".join(value.split()).casefold())


def _identifiers(values: Iterable[str]) -> list[str]:
    return sorted({normalized for value in values if (normalized := exact_identifier(value))})


def _generation(value: str) -> str:
    if not value.strip():
        raise ValueError("generation_id must not be blank")
    return value


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("limit must be a positive integer")
    return min(value, SOURCE_LIMIT)


LEXICAL_SQL = """
WITH query AS (SELECT plainto_tsquery('simple', :query_text) AS terms),
candidates AS (
    SELECT e.*, to_tsvector('simple', COALESCE(e.payload->>'search_text', e.quote)) AS search_vector,
           (SELECT count(*) FROM unnest(CAST(:identifiers AS TEXT[])) AS wanted(identifier)
            WHERE CAST(e.identifiers AS JSONB) ? wanted.identifier) AS exact_matches
    FROM spec_search_chunks AS e
    WHERE e.generation_id = :generation_id
)
SELECT e.*, e.id AS evidence_id,
       ts_rank_cd(e.search_vector, query.terms) AS lexical_score
FROM candidates AS e CROSS JOIN query
WHERE e.search_vector @@ query.terms
   OR e.exact_matches > 0
ORDER BY exact_matches DESC, lexical_score DESC, e.id ASC
LIMIT :limit
"""


def build_lexical_query(
    query: str,
    *,
    generation_id: str,
    identifiers: Iterable[str] = (),
    limit: int = SOURCE_LIMIT,
) -> TextClause:
    """Return executable bound SQL, never execute it.

    Uses spec_search_chunks(generation_id, id, quote, identifiers JSON array, ...).
    Trust classification stays with the caller; all original chunk fields are returned.
    Identifiers must be normalized with exact_identifier at indexing time too.
    """
    return text(LEXICAL_SQL).bindparams(
        bindparam("query_text", value=query, type_=Text()),
        bindparam("generation_id", value=_generation(generation_id), type_=Text()),
        bindparam("identifiers", value=_identifiers(identifiers), type_=ARRAY(Text())),
        bindparam("limit", value=_limit(limit)),
    )


class GraphEvidence(EvidenceHit):
    document_id: str = Field(min_length=1, max_length=200)
    exact_identifiers: tuple[str, ...] = ()
    properties: tuple[str, ...] = ()
    targets: tuple[str, ...] = Field(default=(), max_length=100)

    @field_validator("document_id")
    @classmethod
    def nonblank_document(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document_id must not be blank")
        return value

    @field_validator("exact_identifiers", "properties")
    @classmethod
    def normalize_identifiers(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_identifiers(values))

    @field_validator("targets")
    @classmethod
    def normalize_targets(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(exact_identifier(value) for value in values)
        if any(not value or len(value) > 200 for value in normalized):
            raise ValueError("targets must contain 1-200 characters")
        return tuple(sorted(set(normalized)))


GRAPH_ROW_LIMIT = 3000


class GraphRequirement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    requirement_id: str = Field(min_length=1, max_length=100)
    notice_no: str = Field(min_length=1, max_length=100)
    document_id: str = Field(min_length=1, max_length=200)
    property: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=200)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("property", "target", mode="before")
    @classmethod
    def canonical_terms(cls, value: Any) -> Any:
        return exact_identifier(value) if isinstance(value, str) else value

    @field_validator("requirement_id", "notice_no", "document_id", "property", "target")
    @classmethod
    def nonblank_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("graph requirement fields must not be blank")
        return value


NEO4J_READ = """
MATCH (:SpecDocument {generation_id: $generation_id})-[:HAS_EVIDENCE]->
      (e:SpecEvidence {generation_id: $generation_id})
OPTIONAL MATCH (e)-[:HAS_PROPERTY]->(p:SpecProperty {generation_id: $generation_id})
WITH e, collect(DISTINCT p.value) AS properties
WITH e, size([identifier IN $identifiers WHERE identifier IN e.exact_identifiers]) AS identifier_matches,
     size([property IN $properties WHERE property IN properties]) AS property_matches
WITH e, identifier_matches + property_matches AS matches,
     CASE WHEN identifier_matches > 0 THEN 1 ELSE 2 END AS shortest_hop
WHERE matches > 0
RETURN e.evidence_id AS evidence_id, e.evidence_group AS group,
       e.generation_id AS generation_id, matches, shortest_hop
ORDER BY matches DESC, shortest_hop ASC, evidence_id ASC
LIMIT $limit
"""
NEO4J_UPSERT = """
UNWIND $rows AS row
MERGE (e:SpecEvidence {generation_id: $generation_id, evidence_id: row.evidence_id})
SET e.evidence_group = row.group, e.exact_identifiers = row.exact_identifiers
WITH e, row
OPTIONAL MATCH (old_document:SpecDocument {generation_id: $generation_id})-[old_link:HAS_EVIDENCE]->(e)
WHERE old_document.document_id <> row.document_id
DELETE old_link
WITH DISTINCT e, row
MERGE (d:SpecDocument {generation_id: $generation_id, document_id: row.document_id})
MERGE (d)-[:HAS_EVIDENCE]->(e)
WITH e, row
OPTIONAL MATCH (e)-[old_link:HAS_PROPERTY]->(old_property:SpecProperty {generation_id: $generation_id})
WHERE NOT old_property.value IN row.properties
DELETE old_link
WITH DISTINCT e, row
FOREACH (property IN row.properties |
    MERGE (p:SpecProperty {generation_id: $generation_id, value: property})
    MERGE (e)-[:HAS_PROPERTY]->(p)
)
WITH e, row
OPTIONAL MATCH (e)-[old_link:ABOUT]->(old_product:SpecProduct {generation_id: $generation_id})
WHERE NOT old_product.value IN row.targets
DELETE old_link
WITH DISTINCT e, row
FOREACH (target IN row.targets |
    MERGE (product:SpecProduct {generation_id: $generation_id, value: target})
    MERGE (e)-[:ABOUT]->(product)
)
RETURN count(e) AS count
"""
NEO4J_UPSERT_REQUIREMENTS = """
UNWIND $rows AS row
MERGE (d:SpecDocument {generation_id: $generation_id, document_id: row.document_id})
WITH d, row
WHERE d.source_sha256 IS NULL OR d.source_sha256 = row.source_sha256
SET d.source_sha256 = row.source_sha256
MERGE (n:SpecNotice {generation_id: $generation_id, notice_no: row.notice_no})
MERGE (r:SpecRequirement {generation_id: $generation_id,
                        notice_no: row.notice_no, requirement_id: row.requirement_id})
SET r.source_sha256 = row.source_sha256
MERGE (n)-[:REQUIRES]->(r)
WITH d, r, row
OPTIONAL MATCH (r)-[old_link:REQUIRES_PROPERTY|ABOUT|SOURCED_FROM]->
              (old_node {generation_id: $generation_id})
DELETE old_link
WITH DISTINCT d, r, row
MERGE (p:SpecProperty {generation_id: $generation_id, value: row.property})
MERGE (product:SpecProduct {generation_id: $generation_id, value: row.target})
MERGE (r)-[:REQUIRES_PROPERTY]->(p)
MERGE (r)-[:ABOUT]->(product)
MERGE (r)-[:SOURCED_FROM]->(d)
RETURN count(r) AS count
"""
NEO4J_COUNT = """
MATCH (:SpecDocument {generation_id: $generation_id})-[:HAS_EVIDENCE]->
      (e:SpecEvidence {generation_id: $generation_id})
RETURN count(DISTINCT e) AS count
"""


NEO4J_SCHEMA_STATEMENTS = (
    "CREATE CONSTRAINT spec_evidence_generation_unique IF NOT EXISTS "
    "FOR (n:SpecEvidence) REQUIRE (n.generation_id, n.evidence_id) IS UNIQUE",
    "CREATE CONSTRAINT spec_document_generation_unique IF NOT EXISTS "
    "FOR (n:SpecDocument) REQUIRE (n.generation_id, n.document_id) IS UNIQUE",
    "CREATE CONSTRAINT spec_property_generation_unique IF NOT EXISTS "
    "FOR (n:SpecProperty) REQUIRE (n.generation_id, n.value) IS UNIQUE",
    "CREATE CONSTRAINT spec_product_generation_unique IF NOT EXISTS "
    "FOR (n:SpecProduct) REQUIRE (n.generation_id, n.value) IS UNIQUE",
    "CREATE CONSTRAINT spec_notice_generation_unique IF NOT EXISTS "
    "FOR (n:SpecNotice) REQUIRE (n.generation_id, n.notice_no) IS UNIQUE",
    "CREATE CONSTRAINT spec_requirement_generation_unique IF NOT EXISTS "
    "FOR (n:SpecRequirement) REQUIRE (n.generation_id, n.notice_no, n.requirement_id) IS UNIQUE",
)


def ensure_graph_schema(driver: Any, database: str) -> None:
    """Explicit CLI provisioning only; fixed, idempotent schema statements, no data writes."""
    if not database.strip():
        raise ValueError("database must not be blank")
    with driver.session(database=database) as session:
        for statement in NEO4J_SCHEMA_STATEMENTS:
            session.run(statement).consume()


class Neo4jEvidenceAdapter:
    """Borrow a Neo4j driver. Only the fixed data queries above can be executed.

    Call ensure_graph_schema explicitly outside this adapter before concurrent indexing.
    Notice, requirement, document, property and product identities are generation-scoped.
    No arbitrary Cypher API or automatic schema provisioning.
    Read ranks count identifier/property matches, then shortest distance from the
    document (evidence identifiers: 1 hop; properties: 2 hops), then evidence ID.
    Returned groups are index annotations only: callers must revalidate current trust.
    """

    def __init__(self, driver: Any, *, database: str, generation_id: str) -> None:
        self._driver = driver
        self._database = database
        self._generation_id = _generation(generation_id)

    def read(
        self,
        identifiers: Iterable[str] = (),
        *,
        properties: Iterable[str] = (),
        limit: int = SOURCE_LIMIT,
    ) -> tuple[EvidenceHit, ...]:
        params = {
            "generation_id": self._generation_id,
            "identifiers": _identifiers(identifiers),
            "properties": _identifiers(properties),
            "limit": _limit(limit),
        }
        if not params["identifiers"] and not params["properties"]:
            return ()

        def run(tx: Any) -> tuple[EvidenceHit, ...]:
            result = tx.run(NEO4J_READ, **params)
            hits = []
            for row in islice(result, params["limit"]):
                if row["generation_id"] != self._generation_id:
                    raise ValueError("Neo4j returned a different generation")
                hits.append(EvidenceHit(evidence_id=row["evidence_id"], group=row["group"]))
            return tuple(hits)

        with self._driver.session(database=self._database) as session:
            return session.execute_read(run)

    def upsert(self, evidence: Sequence[GraphEvidence]) -> int:
        if len(evidence) > GRAPH_ROW_LIMIT:
            raise ValueError("graph upsert is limited to 3000 rows")
        rows = [row.model_dump(mode="json") for row in evidence]
        if not rows:
            return 0
        if len({row["evidence_id"] for row in rows}) != len(rows):
            raise ValueError("duplicate evidence IDs in upsert")

        def run(tx: Any) -> int:
            count = int(
                tx.run(
                    NEO4J_UPSERT,
                    generation_id=self._generation_id,
                    rows=rows,
                ).single()["count"]
            )
            if count != len(rows):
                raise ValueError("Neo4j upsert count does not match input")
            return count

        with self._driver.session(database=self._database) as session:
            return session.execute_write(run)

    def upsert_requirements(self, rows: Sequence[GraphRequirement]) -> int:
        """Upsert canonical requirement relationships, checking every row before any write.

        Repeated notice/requirement keys or conflicting document hashes fail closed.
        A stored source-hash mismatch reduces the returned count and rolls back the
        entire managed transaction. Requirements are not included in evidence count().
        """
        if len(rows) > GRAPH_ROW_LIMIT:
            raise ValueError("graph upsert is limited to 3000 rows")
        validated = [GraphRequirement.model_validate(row) for row in rows]
        if not validated:
            return 0
        if len({(row.notice_no, row.requirement_id) for row in validated}) != len(validated):
            raise ValueError("duplicate notice/requirement IDs in upsert")
        hashes: dict[str, str] = {}
        for row in validated:
            if hashes.setdefault(row.document_id, row.source_sha256) != row.source_sha256:
                raise ValueError("conflicting document source hashes in generation")
        payload = [row.model_dump(mode="json") for row in validated]

        def run(tx: Any) -> int:
            count = int(
                tx.run(
                    NEO4J_UPSERT_REQUIREMENTS,
                    generation_id=self._generation_id,
                    rows=payload,
                ).single()["count"]
            )
            if count != len(payload):
                raise ValueError("Neo4j requirement upsert count/source hash mismatch")
            return count

        with self._driver.session(database=self._database) as session:
            return session.execute_write(run)

    def count(self) -> int:
        """Exact attached-evidence count for this pinned generation."""

        def run(tx: Any) -> int:
            return int(tx.run(NEO4J_COUNT, generation_id=self._generation_id).single()["count"])

        with self._driver.session(database=self._database) as session:
            return session.execute_read(run)


def _revision(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("model revision must be an explicit lowercase 40-hex commit SHA")
    return value


def _dense_vector(values: Iterable[float]) -> list[float]:
    vector = [float(value) for value in values]
    if len(vector) != DENSE_DIMENSIONS or not all(math.isfinite(value) for value in vector):
        raise ValueError("BGE-M3 requires 1024 finite dense values")
    if not any(vector):
        raise ValueError("cosine vectors must not be zero")
    return vector


class BgeM3Embedder:
    """Explicit local-only load, followed by dense encoding; no query-time loading.

    snapshot_path must be a pre-provisioned HF snapshots/<commit SHA> directory.
    model_factory is a SentenceTransformer-compatible injectable constructor. The
    caller is responsible for provisioning authentic BAAI/bge-m3 snapshot files.
    """

    def __init__(
        self, *, snapshot_path: str | Path, revision: str, model_factory: Any = None
    ) -> None:
        self._revision = _revision(revision)
        self._snapshot_path = Path(snapshot_path)
        self._model_factory = model_factory
        self._model: Any = None

    @property
    def revision(self) -> str:
        return self._revision

    def load_local(self) -> None:
        if self._model is not None:
            return
        path = self._snapshot_path.resolve(strict=True)
        if not path.is_dir() or path.name != self.revision or path.parent.name != "snapshots":
            raise ValueError("local snapshot path must end in snapshots/<revision>")
        factory = self._model_factory
        if factory is None:
            from sentence_transformers import SentenceTransformer

            factory = SentenceTransformer
        model = factory(
            str(path),
            revision=self.revision,
            local_files_only=True,
            trust_remote_code=False,
            model_kwargs={"weights_only": True},
            device="cpu",
        )
        if model.get_sentence_embedding_dimension() != DENSE_DIMENSIONS:
            raise ValueError("local model is not a 1024-dimensional BGE-M3 model")
        self._model = model

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if self._model is None:
            raise RuntimeError("BGE-M3 is not loaded; call load_local explicitly")
        if not texts:
            return ()
        max_length = self._model.max_seq_length
        if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length < 1:
            raise ValueError("local model must declare a positive max_seq_length")
        tokens = self._model.tokenizer(
            list(texts),
            add_special_tokens=True,
            truncation=False,
            padding=False,
            return_attention_mask=False,
            return_token_type_ids=False,
        )["input_ids"]
        if len(tokens) != len(texts) or any(len(row) > max_length for row in tokens):
            raise ValueError("input exceeds model.max_seq_length; truncation is forbidden")
        encoded = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
            prompt="",
        )
        if len(encoded) != len(texts):
            raise ValueError("embedding output count does not match input")
        return tuple(tuple(_dense_vector(vector)) for vector in encoded)


class VectorEvidence(EvidenceHit):
    vector: tuple[float, ...]

    @field_validator("vector")
    @classmethod
    def validate_vector(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        return tuple(_dense_vector(values))


class TextEvidence(EvidenceHit):
    text: str = Field(min_length=1)


class QdrantEvidenceAdapter:
    """Dedicated generation/revision collection, raw dense vectors only, no FastEmbed.

    Collection provisioning is explicit. Search/upsert never create or repair collections.
    SDK models import lazily, or can be replaced by a compatible fake via models=.
    Returned groups are index annotations only: callers must revalidate current trust.
    """

    def __init__(
        self,
        client: Any,
        *,
        generation_id: str,
        revision: str,
        models: Any = None,
    ) -> None:
        self._client = client
        self._generation_id = _generation(generation_id)
        self._revision = _revision(revision)
        generation_hash = hashlib.sha256(generation_id.encode("utf-8")).hexdigest()
        self._collection = f"specifications_bge_m3_{generation_hash}_{self._revision}"
        self._sdk_models = models

    @property
    def collection_name(self) -> str:
        return self._collection

    def _models(self) -> Any:
        if self._sdk_models is None:
            from qdrant_client import models

            self._sdk_models = models
        return self._sdk_models

    def _validate_collection(self) -> None:
        vectors = self._client.get_collection(self.collection_name).config.params.vectors
        if (
            isinstance(vectors, dict)
            or vectors.size != DENSE_DIMENSIONS
            or vectors.distance != self._models().Distance.COSINE
        ):
            raise ValueError("specification collection must use unnamed dense1024 cosine vectors")

    def ensure_collection(self) -> None:
        if not self._client.collection_exists(self.collection_name):
            models = self._models()
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=DENSE_DIMENSIONS, distance=models.Distance.COSINE
                ),
            )
        self._validate_collection()

    def count(self) -> int:
        """Exact point count of this generation/revision collection, without creation."""
        self._validate_collection()
        return int(self._client.count(collection_name=self.collection_name, exact=True).count)

    def index(self, evidence: Sequence[TextEvidence], *, embedder: BgeM3Embedder) -> int:
        """Explicit indexing: encode locally, provision collection, then upsert.

        The caller must already have called embedder.load_local(). No load, download,
        fallback, or replacement of a mismatched collection is performed here.
        """
        self._check_embedder(embedder)
        if len({row.evidence_id for row in evidence}) != len(evidence):
            raise ValueError("duplicate evidence IDs in index")
        vectors = embedder.embed([row.text for row in evidence])
        if not evidence:
            return 0
        rows = [
            VectorEvidence(evidence_id=row.evidence_id, group=row.group, vector=vector)
            for row, vector in zip(evidence, vectors, strict=True)
        ]
        self.ensure_collection()
        self.upsert(rows)
        return len(rows)

    def query(
        self,
        text: str,
        *,
        embedder: BgeM3Embedder,
        limit: int = SOURCE_LIMIT,
    ) -> tuple[EvidenceHit, ...]:
        """Encode with an already loaded, revision-matched local model, then search."""
        self._check_embedder(embedder)
        limit = _limit(limit)
        return self.search(embedder.embed([text])[0], limit=limit)

    def _check_embedder(self, embedder: BgeM3Embedder) -> None:
        if embedder.revision != self._revision:
            raise ValueError("embedder revision does not match the generation collection")

    def upsert(self, evidence: Sequence[VectorEvidence]) -> None:
        if not evidence:
            return
        if len({row.evidence_id for row in evidence}) != len(evidence):
            raise ValueError("duplicate evidence IDs in upsert")
        self._validate_collection()
        models = self._models()
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.collection_name}:{row.evidence_id}")),
                vector=list(row.vector),
                payload={
                    "evidence_id": row.evidence_id,
                    "group": row.group,
                    "generation_id": self._generation_id,
                    "model_id": BGE_M3_MODEL,
                    "model_revision": self._revision,
                },
            )
            for row in evidence
        ]
        self._client.upsert(collection_name=self.collection_name, points=points, wait=True)

    def search(
        self, vector: Iterable[float], *, limit: int = SOURCE_LIMIT
    ) -> tuple[EvidenceHit, ...]:
        values, limit = _dense_vector(vector), _limit(limit)
        self._validate_collection()
        points = self._client.query_points(
            collection_name=self.collection_name,
            query=values,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        ).points
        hits = []
        for point in islice(points, limit):
            payload = point.payload or {}
            if (
                payload.get("generation_id") != self._generation_id
                or payload.get("model_revision") != self._revision
                or payload.get("model_id") != BGE_M3_MODEL
            ):
                raise ValueError("Qdrant returned incompatible evidence provenance")
            score = float(point.score)
            if not math.isfinite(score):
                raise ValueError("Qdrant returned a non-finite score")
            hits.append(
                (
                    score,
                    EvidenceHit(
                        evidence_id=payload["evidence_id"],
                        group=payload["group"],
                    ),
                )
            )
        return tuple(
            hit for _, hit in sorted(hits, key=lambda pair: (-pair[0], pair[1].evidence_id))
        )
