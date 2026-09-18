"""Generation snapshots with fenced publication and current-source retrieval."""
from __future__ import annotations

import os
import re
from contextlib import closing, contextmanager
from datetime import timedelta
from functools import lru_cache

from pydantic import ValidationError
from sqlalchemy import delete, select, update

from api.specifications.models import SearchRequest, Specification
from api.specifications.retrieval import (
    BgeM3Embedder,
    EvidenceHit,
    GraphEvidence,
    GraphRequirement,
    Neo4jEvidenceAdapter,
    QdrantEvidenceAdapter,
    VectorEvidence,
    build_lexical_query,
    ensure_graph_schema,
    exact_identifier,
    reciprocal_rank_fusion,
)
from api.specifications.service import document, require_enabled, verified_evidence
from api.specifications.table_structure import context_for_span
from api.specifications.tables import active_indexes, chunks, generations
from api.specifications.validation import VERSION, compare, parse_numeric, sha, validate_spec
from api.workspace import service
from api.workspace.asset_policy import document_issue
from api.workspace.errors import HANDLED_ERRORS
from api.workspace.execution import source_path
from api.workspace.tables import jobs

GRAPH_SCHEMA_VERSION = "spec-graph-v2-notice-requirement-product"


def configuration() -> dict:
    revision = os.getenv("SPEC_BGE_REVISION", "")
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        service.fail("spec_model_not_configured", "BGE-M3의 고정 모델 리비전을 등록하세요.", status=503)
    return {"model": "BAAI/bge-m3", "revision": revision, "dimension": 1024, "metric": "Cosine",
            "chunking": "paragraph-600-table-context-v2", "normalization": VERSION,
            "graph_schema_version": GRAPH_SCHEMA_VERSION,
            "snapshot_path": os.getenv("SPEC_BGE_SNAPSHOT", "")}


@lru_cache(maxsize=2)
def embedder(snapshot: str, revision: str):
    model = BgeM3Embedder(snapshot_path=snapshot, revision=revision)
    model.load_local()
    return model


@contextmanager
def graph_driver():
    from neo4j import GraphDatabase
    uri, password = os.getenv("SPEC_NEO4J_URI", ""), os.getenv("SPEC_NEO4J_PASSWORD", "")
    if not uri or not password:
        raise ValueError("graph_not_configured")
    with GraphDatabase.driver(uri, auth=(os.getenv("SPEC_NEO4J_USER", "neo4j"), password),
            connection_timeout=5, max_transaction_retry_time=0) as driver:
        yield driver


@contextmanager
def graph_adapter(generation_id: str):
    with graph_driver() as driver:
        yield Neo4jEvidenceAdapter(driver, database="neo4j", generation_id=generation_id)


def provision_graph_schema() -> None:
    """Explicit validation-environment CLI setup; never invoked by indexing/search."""
    require_enabled()
    with graph_driver() as driver:
        ensure_graph_schema(driver, "neo4j")


def _graph_requirements(notice_no: str, inputs: dict) -> list[GraphRequirement]:
    """Project the specifications whose sources make_chunks has just revalidated."""
    result = []
    for requirement_id, record in sorted(inputs.get("specifications", {}).items()):
        if record["validation"]["status"] != "valid":
            continue
        spec = Specification.model_validate(record["payload"])
        result.append(GraphRequirement(
            requirement_id=requirement_id, notice_no=notice_no,
            document_id=spec.source.document_id, property=spec.property, target=spec.target,
            source_sha256=spec.source.document_sha256,
        ))
    return result


@contextmanager
def vector_adapter(generation_id: str, manifest: dict):
    from qdrant_client import QdrantClient
    url = os.getenv("SPEC_QDRANT_URL", "")
    if not url:
        raise ValueError("vector_not_configured")
    with closing(QdrantClient(url=url, api_key=os.getenv("SPEC_QDRANT_API_KEY") or None, timeout=10)) as client:
        yield QdrantEvidenceAdapter(client, generation_id=generation_id, revision=manifest["revision"])


def group_for(doc: dict, inputs: dict) -> str:
    return "trusted" if verified_evidence(doc, inputs) else "reference"


def spans(text: str):
    # Keep every character; source spans, not rewritten summaries, are indexed.
    for match in re.finditer(r"[^\n]+(?:\n|$)", text):
        for start in range(match.start(), match.end(), 600):
            end = min(start + 600, match.end())
            if text[start:end].strip():
                yield start, end


def make_chunks(inputs: dict) -> list[dict]:
    rows = []
    req_specs = [Specification.model_validate(v["payload"]) for v in inputs.get("specifications", {}).values()
                 if v["validation"]["status"] == "valid"]
    for requirement in req_specs:
        origin = document(inputs, requirement.source.document_id)
        if not origin or validate_spec(requirement, origin)["status"] != "valid":
            service.fail("spec_source_changed", "사양 원문이 변경되었습니다. 먼저 재검토하세요.")
        source_path(origin)
    for doc in inputs.get("documents", []):
        if doc.get("role") not in {"company_evidence", "product_evidence", "company_reference"} or not doc.get("text"):
            continue
        if document_issue(doc, inputs.get("company") or {}):
            continue
        source_path(doc)
        if not doc.get("sha256"):
            continue
        text = doc["text"]
        for start, end in spans(text):
            quote = text[start:end]
            extraction = doc.get("extraction") or {}
            table_context = context_for_span(extraction, text, start, end) if extraction.get("tables") else None
            search_text = quote
            if table_context and table_context["status"] == "matched" and not table_context["needs_review"]:
                search_text += "\n" + table_context["text"]
            observations = []
            identifiers = []
            complete_statement = (start == 0 or text[start - 1] == "\n") and (end == len(text) or text[end - 1] == "\n")
            for req in req_specs if complete_statement else []:
                evidence = req.model_copy(deep=True)
                evidence.raw = quote
                evidence.conditions = ""
                evidence.source = req.source.model_copy(update={"document_id": doc["id"], "document_sha256": doc["sha256"],
                    "text_sha256": sha(text), "start": start, "end": end, "quote": quote, "locator": f"문자 {start}:{end}"})
                if req.kind == "identifier":
                    if re.search(r"(?<!\w)" + re.escape(req.identifier) + r"(?!\w)", quote, re.I):
                        identifiers.append(exact_identifier(req.identifier))
                    else:
                        continue
                elif req.kind == "numeric":
                    parsed = parse_numeric(quote)
                    if "code" in parsed:
                        continue
                    evidence.operator, evidence.value, evidence.unit = parsed["operator"], parsed.get("value"), parsed["unit"]
                    evidence.lower, evidence.upper = parsed.get("lower"), parsed.get("upper")
                    evidence.uncertainty = parsed.get("uncertainty")
                    evidence.tolerance = parsed.get("tolerance")
                else:
                    continue
                if validate_spec(evidence, doc)["status"] == "valid":
                    observations.append(evidence.model_dump(mode="json"))
            identity = sha(f"{doc['id']}:{doc['sha256']}:{sha(text)}:{start}:{end}")
            rows.append({"id": identity, "document_id": doc["id"], "document_sha256": doc["sha256"],
                "text_sha256": sha(text), "quote": quote, "locator": f"문자 {start}:{end}", "start": start, "end": end,
                "identifiers": sorted(set(identifiers)), "properties": sorted({v["property"] for v in observations}),
                "payload": {"observations": observations, "group": group_for(doc, inputs),
                            "search_text": search_text, "table_context": table_context}})
            if len(rows) > 3000:
                service.fail("spec_index_too_large", "사양 검색 자료가 단일 작업 한도를 초과했습니다.",
                             "자료를 나누어 등록하세요. 내용은 잘라서 색인하지 않습니다.")
    return rows


def fence(conn, job: dict):
    ws = service.load(conn, job["notice_no"], job["input_version"])
    service.assert_source_current(conn, ws)
    current = conn.execute(select(jobs).where(jobs.c.id == job["id"])).mappings().first()
    if not current or current["status"] != "running" or current["claim_token"] != job["claim_token"]:
        service.fail("spec_claim_lost", "색인 작업의 실행 권한이 만료되었습니다.")
    if service.digest(ws["inputs"]) != service.digest(job["snapshot"]):
        service.fail("version_conflict", "색인 중 입력이 변경되었습니다.")
    return ws


def build(engine, job: dict) -> dict:
    require_enabled()
    manifest = configuration()
    rows = make_chunks(job["snapshot"])
    if not rows:
        service.fail("spec_evidence_missing", "검색할 회사·제품 참고자료가 없습니다.")
    graph_requirements = _graph_requirements(job["notice_no"], job["snapshot"])
    manifest["graph_requirements_hash"] = service.digest([
        row.model_dump(mode="json") for row in graph_requirements
    ])
    manifest["content_hash"] = service.digest(rows)
    manifest["count"] = len(rows)
    with engine.begin() as conn:
        fence(conn, job)
        prior = conn.execute(select(generations).where(generations.c.notice_no == job["notice_no"],
            generations.c.input_version == job["input_version"],
            generations.c.input_hash == service.digest(job["snapshot"]), generations.c.status.in_(["building", "failed"]))
            .order_by(generations.c.created_at.desc())).mappings().all()
        generation = next((dict(g) for g in prior if g["manifest"] == manifest), None)
        if generation is None:
            generation = {"id": service.uid(), "notice_no": job["notice_no"], "job_id": job["id"],
                "input_version": job["input_version"], "input_hash": service.digest(job["snapshot"]),
                "manifest": manifest, "stores": {}, "status": "building", "created_at": service.now()}
            conn.execute(generations.insert().values(**generation))
        else:
            conn.execute(update(generations).where(generations.c.id == generation["id"]).values(job_id=job["id"], status="building"))
        gid = generation["id"]
    stores = dict(generation["stores"])
    for store in ("lexical", "graph", "dense"):
        if stores.get(store, {}).get("status") == "succeeded":
            continue
        try:
            if store == "lexical":
                with engine.begin() as conn:
                    fence(conn, job)
                    conn.execute(delete(chunks).where(chunks.c.generation_id == gid))
                    conn.execute(chunks.insert(), [{**r, "generation_id": gid} for r in rows])
            elif store == "graph":
                with graph_adapter(gid) as graph:
                    if graph.upsert_requirements(graph_requirements) != len(graph_requirements):
                        raise ValueError("graph_requirement_count_mismatch")
                    count = graph.upsert([GraphEvidence(evidence_id=r["id"], group=r["payload"]["group"],
                        exact_identifiers=tuple(r["identifiers"]), properties=tuple(r["properties"]),
                        targets=tuple(sorted({v["target"] for v in r["payload"]["observations"]})),
                        document_id=r["document_id"]) for r in rows])
                    if count != len(rows) or graph.count() != len(rows):
                        raise ValueError("graph_count_mismatch")
            else:
                model = embedder(manifest["snapshot_path"], manifest["revision"])
                with vector_adapter(gid, manifest) as vector:
                    vector.ensure_collection()
                    for offset in range(0, len(rows), 16):
                        batch = rows[offset:offset + 16]
                        embeddings = model.embed([r["payload"]["search_text"] for r in batch])
                        vector.upsert([VectorEvidence(evidence_id=r["id"], group=r["payload"]["group"], vector=v)
                                       for r, v in zip(batch, embeddings, strict=True)])
                        with engine.begin() as conn:
                            fence(conn, job)
                    if vector.count() != len(rows):
                        raise ValueError("vector_count_mismatch")
            stores[store] = {"status": "succeeded", "count": len(rows), "content_hash": manifest["content_hash"]}
        except Exception as exc:
            # Only classified codes are persisted, not credentials, source text or SDK responses.
            if isinstance(exc, HANDLED_ERRORS):
                raise
            stores[store] = {"status": "failed", "code": f"{store}_unavailable"}
        with engine.begin() as conn:
            fence(conn, job)
            conn.execute(update(generations).where(generations.c.id == gid).values(stores=stores))
    complete = all(stores.get(s, {}).get("status") == "succeeded" for s in ("lexical", "graph", "dense"))
    with engine.begin() as conn:
        fence(conn, job)
        conn.execute(update(generations).where(generations.c.id == gid).values(status="ready" if complete else "failed"))
    return {"generation": gid, "stores": stores, "manifest_hash": service.digest(manifest),
            "warnings": ["검색 평가 및 명시적 공개 전 검증용 색인입니다."] if complete else ["일부 검색 저장소 색인 실패; 기존 검색 유지"],
            "ready_for_evaluation": complete}


def publish(conn, notice_no: str, generation_id: str, report: dict) -> None:
    """Explicit CLI release only, following frozen-set evaluation; never from build."""
    require_enabled()
    from api.specifications.evaluation import release_gate
    ws = service.load(conn, notice_no)
    service.assert_source_current(conn, ws)
    generation = conn.execute(select(generations).where(generations.c.id == generation_id,
                             generations.c.notice_no == notice_no)).mappings().first()
    if not generation or generation["status"] != "ready" or generation["input_version"] != ws["version"] or generation["input_hash"] != service.digest(ws["inputs"]):
        service.fail("spec_generation_stale", "최신 입력으로 완료된 검색 색인이 필요합니다.")
    job = conn.execute(select(jobs).where(jobs.c.id == generation["job_id"])).mappings().first()
    if not job or job["status"] != "succeeded" or job["input_version"] != ws["version"]:
        service.fail("spec_job_incomplete", "색인 실행의 완료 기록을 먼저 확인하세요.")
    if not release_gate(report, service.digest(generation["manifest"])):
        service.fail("spec_evaluation_failed", "홀드아웃·안전 평가를 통과한 검증 기록이 필요합니다.")
    old = conn.execute(select(active_indexes).where(active_indexes.c.notice_no == notice_no)).mappings().first()
    if old:
        conn.execute(update(generations).where(generations.c.id == old["generation_id"]).values(retire_after=service.now() + timedelta(days=7)))
        conn.execute(update(active_indexes).where(active_indexes.c.notice_no == notice_no).values(generation_id=generation_id))
    else:
        conn.execute(active_indexes.insert().values(notice_no=notice_no, generation_id=generation_id))
    service.audit(conn, ws, "spec_index_publish", "검증된 검색 색인 공개; 업무 승인 아님",
                  {"generation": generation_id, "previous": old["generation_id"] if old else None, "report_hash": service.digest(report)})


def search(engine, notice_no: str, body: SearchRequest, *, generation_id: str | None = None) -> dict:
    reasons = []
    empty = {"groups": {"verified": [], "references": [], "conflicts": []}, "degraded": True, "generation": None}
    with engine.begin() as conn:
        ws = service.load(conn, notice_no)
        service.assert_source_current(conn, ws)
        if generation_id is None:
            generation_id = conn.execute(select(active_indexes.c.generation_id).where(active_indexes.c.notice_no == notice_no)).scalar()
        generation = conn.execute(select(generations).where(generations.c.id == generation_id,
                             generations.c.notice_no == notice_no)).mappings().first() if generation_id else None
        if not generation:
            return {**empty, "reasons": ["검증·공개된 검색 색인이 없습니다."]}
        if generation["input_version"] != ws["version"] or generation["input_hash"] != service.digest(ws["inputs"]):
            return {**empty, "reasons": ["입력이 변경되어 검색 색인을 다시 만들어야 합니다."]}
        rows = [dict(r) for r in conn.execute(select(chunks).where(chunks.c.generation_id == generation_id)).mappings()]
        req_record = ws["inputs"].get("specifications", {}).get(body.requirement_id)
        requirement = Specification.model_validate(req_record["payload"]) if req_record else None
        if body.requirement_id and not requirement:
            service.fail("spec_not_found", "검증할 요구 사양을 선택하세요.", status=404)
        if requirement and validate_spec(requirement, document(ws["inputs"], requirement.source.document_id))["status"] != "valid":
            service.fail("spec_unverified", "요구 사양의 원문·단위를 먼저 교정하세요.")
        if requirement:
            source_path(document(ws["inputs"], requirement.source.document_id))
        query = body.query.strip() or (requirement.raw if requirement else "")
        if not query:
            service.fail("query_required", "검색어 또는 요구 사양을 선택하세요.", status=422)
        ids = [requirement.identifier] if requirement and requirement.kind == "identifier" else [query]
        lexical = []
        if conn.dialect.name == "postgresql":
            lexical = [r["evidence_id"] for r in conn.execute(build_lexical_query(query,
                        generation_id=generation_id, identifiers=ids)).mappings()]
        else:
            reasons.append("PostgreSQL 전문 검색 미연결; 검증용 정확 문자열 검색")
            ranked = [(sum(exact_identifier(i) in r["identifiers"] for i in ids),
                       sum(t in r["payload"].get("search_text", r["quote"]).casefold() for t in query.casefold().split()), r["id"]) for r in rows]
            lexical = [r[2] for r in sorted(ranked, key=lambda v: (-v[0], -v[1], v[2])) if r[0] or r[1]][:100]
    graph_hits, dense_hits = [], []
    try:
        with graph_adapter(generation_id) as graph:
            graph_hits = [h.evidence_id for h in graph.read(ids, properties=[requirement.property] if requirement else [])]
    except Exception:
        reasons.append("그래프 검색 미연결")
    try:
        manifest = generation["manifest"]
        model = embedder(manifest["snapshot_path"], manifest["revision"])
        with vector_adapter(generation_id, manifest) as vector:
            dense_hits = [h.evidence_id for h in vector.search(model.embed([query])[0])]
    except Exception:
        reasons.append("BGE-M3 벡터 검색 미연결")
    # Recheck authoritative inputs AFTER external calls, including expiry and file bytes.
    with engine.begin() as conn:
        fresh = service.load(conn, notice_no)
        service.assert_source_current(conn, fresh)
        if fresh["version"] != generation["input_version"] or service.digest(fresh["inputs"]) != generation["input_hash"]:
            return {**empty, "reasons": ["검색 중 입력이 변경되었습니다. 다시 검색하세요."]}
        if requirement:
            source_path(document(fresh["inputs"], requirement.source.document_id))
        candidates = {}
        for row in rows:
            doc = document(fresh["inputs"], row["document_id"])
            if not doc or document_issue(doc, fresh["inputs"].get("company") or {}):
                continue
            text = doc.get("text") or ""
            if doc.get("sha256") != row["document_sha256"] or sha(text) != row["text_sha256"] or text[row["start"]:row["end"]] != row["quote"]:
                continue
            try:
                source_path(doc)
            except Exception:
                continue
            group = group_for(doc, fresh["inputs"])
            comparisons = []
            if requirement:
                for value in row["payload"].get("observations", []):
                    try:
                        observation = Specification.model_validate(value)
                        if validate_spec(observation, doc)["status"] == "valid":
                            comparisons.append(compare(requirement, observation))
                    except ValidationError:
                        continue
            compliance = "does_not_meet" if "does_not_meet" in comparisons else "meets" if "meets" in comparisons and group == "trusted" else "unassessed"
            if compliance == "does_not_meet":
                group = "conflicts"
            candidates[row["id"]] = {"id": row["id"], "document_id": row["document_id"],
                "quote": row["quote"], "locator": row["locator"], "group": group, "compliance": compliance,
                "table_context": row["payload"].get("table_context"),
                "reason": "검증된 사양 조건 비교" if comparisons else "문구·관계 검색; 적합 판정 아님"}
        def hits(values):
            return [EvidenceHit(evidence_id=i, group=candidates[i]["group"]) for i in values if i in candidates]
        fused = reciprocal_rank_fusion(hits(lexical), hits(dense_hits), hits(graph_hits))
        groups = {}
        for origin, target in (("trusted", "verified"), ("reference", "references"), ("conflicts", "conflicts")):
            groups[target] = [{**candidates[h.evidence_id], "rrf": h.score,
                "ranks": {("dense" if k == "vector" else k): v for k, v in h.ranks.items()}}
                for h in getattr(fused, origin)[:body.limit]]
        return {"groups": groups, "degraded": bool(reasons), "reasons": reasons, "generation": generation_id}
