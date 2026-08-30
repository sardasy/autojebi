from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, update

from api.auth import verify_api_key
from api.db import require_engine
from api.models.proposals import (
    ProjectPerformanceCreate,
    ProjectPerformanceRecord,
    ProposalAnalyzeResponse,
    ProposalCoverageResponse,
    ProposalDocumentCreate,
    ProposalDocumentRecord,
    ProposalGenerateResponse,
    ProposalRetrieveResponse,
    ProposalVerifyResponse,
)
from api.routers.notices import (
    bid_pipeline,
    document_chunks,
    notice_requirements,
    notice_spec_items,
    project_performances,
    proposal_documents,
    proposal_sections,
    requirement_evidences,
)
from api.services.proposal_agent import (
    SECTION_BY_TYPE,
    build_section,
    coverage_items,
    extract_requirements_from_notice,
    row_to_evidence,
    row_to_requirement,
    row_to_section,
    score_chunk,
    score_performance,
    verify_sections,
)

router = APIRouter(
    prefix="/proposals",
    tags=["proposals"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/documents", response_model=ProposalDocumentRecord)
def create_proposal_document(body: ProposalDocumentCreate) -> ProposalDocumentRecord:
    engine = require_engine()
    document_id = _new_id("doc")
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            proposal_documents.insert().values(
                id=document_id,
                title=body.title,
                file_name=body.file_name,
                file_path=body.file_path,
                document_type=body.document_type,
                category=body.category,
                project_name=body.project_name,
                customer_name=body.customer_name,
                checksum=body.checksum,
                indexing_status="indexed" if body.chunks else "pending",
                document_metadata=body.document_metadata,
                created_at=now,
                updated_at=now,
            )
        )
        for chunk in body.chunks:
            conn.execute(
                document_chunks.insert().values(
                    id=_new_id("chunk"),
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    heading=chunk.heading,
                    content=chunk.content,
                    token_count=len(chunk.content.split()),
                    chunk_metadata=chunk.chunk_metadata,
                    created_at=now,
                )
            )
        row = conn.execute(
            select(proposal_documents).where(proposal_documents.c.id == document_id)
        ).mappings().one()
    return _document_to_model(dict(row), body.chunks)


@router.post("/performances", response_model=ProjectPerformanceRecord)
def create_project_performance(body: ProjectPerformanceCreate) -> ProjectPerformanceRecord:
    engine = require_engine()
    performance_id = _new_id("perf")
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        if body.evidence_document_id:
            exists = conn.execute(
                select(proposal_documents.c.id).where(
                    proposal_documents.c.id == body.evidence_document_id
                )
            ).scalar_one_or_none()
            if not exists:
                raise HTTPException(status_code=404, detail="evidence document not found")
        conn.execute(
            project_performances.insert().values(
                id=performance_id,
                project_name=body.project_name,
                customer_name=body.customer_name,
                contract_date=body.contract_date,
                completion_date=body.completion_date,
                contract_amount=body.contract_amount,
                project_type=body.project_type,
                technologies=body.technologies,
                products=body.products,
                description=body.description,
                evidence_document_id=body.evidence_document_id,
                verified=body.verified,
                created_at=now,
                updated_at=now,
            )
        )
        row = conn.execute(
            select(project_performances).where(project_performances.c.id == performance_id)
        ).mappings().one()
    return _performance_to_model(dict(row))


@router.post("/analyze/{notice_no}", response_model=ProposalAnalyzeResponse)
def analyze_notice_for_proposal(notice_no: str) -> ProposalAnalyzeResponse:
    engine = require_engine()
    with engine.begin() as conn:
        row = _load_notice(conn, notice_no)
        spec_rows = _list_spec_rows(conn, notice_no)
        candidates = extract_requirements_from_notice(row, spec_rows)
        conn.execute(delete(notice_requirements).where(notice_requirements.c.notice_no == notice_no))
        for candidate in candidates:
            conn.execute(
                notice_requirements.insert().values(
                    id=_new_id("req"),
                    notice_no=notice_no,
                    **candidate,
                    created_at=datetime.now(tz=UTC),
                    updated_at=datetime.now(tz=UTC),
                )
            )
        requirements = _list_requirements(conn, notice_no)
    return ProposalAnalyzeResponse(notice_no=notice_no, requirements=requirements)


@router.post("/{notice_no}/retrieve", response_model=ProposalRetrieveResponse)
def retrieve_evidence_for_notice(notice_no: str) -> ProposalRetrieveResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _load_notice(conn, notice_no)
        requirements = [item.model_dump() for item in _list_requirements(conn, notice_no)]
        if not requirements:
            raise HTTPException(status_code=409, detail="run proposal analyze first")
        conn.execute(
            delete(requirement_evidences).where(
                requirement_evidences.c.requirement_id.in_([item["id"] for item in requirements])
            )
        )
        documents = [dict(row) for row in conn.execute(select(proposal_documents)).mappings()]
        chunks = [dict(row) for row in conn.execute(select(document_chunks)).mappings()]
        chunks_by_doc: dict[str, list[dict[str, Any]]] = {}
        for chunk in chunks:
            chunks_by_doc.setdefault(str(chunk["document_id"]), []).append(chunk)
        performances = [dict(row) for row in conn.execute(select(project_performances)).mappings()]

        for requirement in requirements:
            scored: list[dict[str, Any]] = []
            for document in documents:
                for chunk in chunks_by_doc.get(str(document["id"]), []):
                    score = score_chunk(requirement, chunk, document)
                    if score > 0:
                        scored.append(
                            {
                                "document_id": document["id"],
                                "chunk_id": chunk["id"],
                                "performance_id": None,
                                "evidence_type": "chunk",
                                "relevance_score": score,
                                "confidence_score": score,
                                "quoted_text": _compact(str(chunk["content"]), 500),
                                "reasoning_summary": f"{document['title']} / {chunk.get('heading') or '본문'}",
                            }
                        )
            for performance in performances:
                score = score_performance(requirement, performance)
                if score > 0:
                    scored.append(
                        {
                            "document_id": performance.get("evidence_document_id"),
                            "chunk_id": None,
                            "performance_id": performance["id"],
                            "evidence_type": "performance",
                            "relevance_score": score,
                            "confidence_score": min(1.0, score + (0.1 if performance.get("verified") else 0)),
                            "quoted_text": _performance_quote(performance),
                            "reasoning_summary": "검증된 실적 DB" if performance.get("verified") else "실적 DB",
                        }
                    )
            for evidence in sorted(scored, key=lambda item: item["relevance_score"], reverse=True)[:5]:
                conn.execute(
                    requirement_evidences.insert().values(
                        id=_new_id("ev"),
                        requirement_id=requirement["id"],
                        approved=False,
                        created_at=datetime.now(tz=UTC),
                        **evidence,
                    )
                )
        evidences = _list_evidences(conn, notice_no)
    return ProposalRetrieveResponse(notice_no=notice_no, evidences=evidences)


@router.post("/{notice_no}/generate", response_model=ProposalGenerateResponse)
def generate_proposal_sections(notice_no: str) -> ProposalGenerateResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _load_notice(conn, notice_no)
        requirements = [item.model_dump() for item in _list_requirements(conn, notice_no)]
        if not requirements:
            raise HTTPException(status_code=409, detail="run proposal analyze first")
        evidences = [item.model_dump() for item in _list_evidences(conn, notice_no)]
        by_type: dict[str, list[dict[str, Any]]] = {}
        for requirement in requirements:
            by_type.setdefault(str(requirement["requirement_type"]), []).append(requirement)
        evidence_by_req: dict[str, list[dict[str, Any]]] = {}
        for evidence in evidences:
            evidence_by_req.setdefault(str(evidence["requirement_id"]), []).append(evidence)

        conn.execute(delete(proposal_sections).where(proposal_sections.c.notice_no == notice_no))
        for req_type, reqs in by_type.items():
            section_key, section_title = SECTION_BY_TYPE.get(req_type, SECTION_BY_TYPE["other"])
            related_evidence = [
                evidence
                for req in reqs
                for evidence in evidence_by_req.get(str(req["id"]), [])[:3]
            ]
            section = build_section(
                notice_no=notice_no,
                section_key=section_key,
                section_title=section_title,
                requirements=reqs,
                evidences=related_evidence,
            )
            conn.execute(proposal_sections.insert().values(id=_new_id("sec"), **section))
        sections = _list_sections(conn, notice_no)
    return ProposalGenerateResponse(notice_no=notice_no, sections=sections)


@router.post("/{notice_no}/verify", response_model=ProposalVerifyResponse)
def verify_proposal_sections(notice_no: str) -> ProposalVerifyResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _load_notice(conn, notice_no)
        sections = [item.model_dump() for item in _list_sections(conn, notice_no)]
        if not sections:
            raise HTTPException(status_code=409, detail="run proposal generate first")
        evidence_ids = {item.id for item in _list_evidences(conn, notice_no)}
        verified = verify_sections(sections, evidence_ids)
        for section in verified:
            conn.execute(
                update(proposal_sections)
                .where(proposal_sections.c.id == section["id"])
                .values(
                    generation_status=section["generation_status"],
                    fact_check_status=section["fact_check_status"],
                    fact_check_notes=section["fact_check_notes"],
                    updated_at=datetime.now(tz=UTC),
                )
            )
        saved = _list_sections(conn, notice_no)
    overall = _overall_status(saved)
    return ProposalVerifyResponse(notice_no=notice_no, sections=saved, status=overall)


@router.get("/{notice_no}/coverage", response_model=ProposalCoverageResponse)
def get_proposal_coverage(notice_no: str) -> ProposalCoverageResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _load_notice(conn, notice_no)
        requirements = [item.model_dump() for item in _list_requirements(conn, notice_no)]
        evidences = [item.model_dump() for item in _list_evidences(conn, notice_no)]
    score, items = coverage_items(requirements, evidences)
    return ProposalCoverageResponse(notice_no=notice_no, readiness_score=score, items=items)


def _load_notice(conn, notice_no: str) -> dict[str, Any]:
    row = conn.execute(
        select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="notice not found")
    return dict(row)


def _list_spec_rows(conn, notice_no: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            select(notice_spec_items).where(notice_spec_items.c.notice_no == notice_no)
        ).mappings()
    ]


def _list_requirements(conn, notice_no: str) -> list:
    return [
        row_to_requirement(dict(row))
        for row in conn.execute(
            select(notice_requirements)
            .where(notice_requirements.c.notice_no == notice_no)
            .order_by(notice_requirements.c.requirement_type, notice_requirements.c.id)
        ).mappings()
    ]


def _list_evidences(conn, notice_no: str) -> list:
    rows = conn.execute(
        select(requirement_evidences)
        .select_from(
            requirement_evidences.join(
                notice_requirements,
                requirement_evidences.c.requirement_id == notice_requirements.c.id,
            )
        )
        .where(notice_requirements.c.notice_no == notice_no)
        .order_by(requirement_evidences.c.relevance_score.desc(), requirement_evidences.c.id)
    ).mappings()
    return [row_to_evidence(dict(row)) for row in rows]


def _list_sections(conn, notice_no: str) -> list:
    return [
        row_to_section(dict(row))
        for row in conn.execute(
            select(proposal_sections)
            .where(proposal_sections.c.notice_no == notice_no)
            .order_by(proposal_sections.c.section_key, proposal_sections.c.version)
        ).mappings()
    ]


def _document_to_model(row: dict[str, Any], chunks: list) -> ProposalDocumentRecord:
    return ProposalDocumentRecord(
        id=str(row["id"]),
        title=str(row["title"]),
        file_name=row.get("file_name"),
        file_path=row.get("file_path"),
        document_type=row.get("document_type"),
        category=row["category"],
        project_name=row.get("project_name"),
        customer_name=row.get("customer_name"),
        checksum=row.get("checksum"),
        indexing_status=row.get("indexing_status") or "pending",
        document_metadata=dict(row.get("document_metadata") or {}),
        chunks=chunks,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _performance_to_model(row: dict[str, Any]) -> ProjectPerformanceRecord:
    return ProjectPerformanceRecord(
        id=str(row["id"]),
        project_name=str(row["project_name"]),
        customer_name=row.get("customer_name"),
        contract_date=row.get("contract_date"),
        completion_date=row.get("completion_date"),
        contract_amount=float(row["contract_amount"]) if row.get("contract_amount") is not None else None,
        project_type=row.get("project_type"),
        technologies=list(row.get("technologies") or []),
        products=list(row.get("products") or []),
        description=row.get("description"),
        evidence_document_id=row.get("evidence_document_id"),
        verified=bool(row.get("verified")),
    )


def _performance_quote(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("project_name") or ""),
        str(row.get("customer_name") or ""),
        str(row.get("project_type") or ""),
        ", ".join(row.get("technologies") or []),
        ", ".join(row.get("products") or []),
        str(row.get("description") or ""),
    ]
    return _compact(" / ".join(part for part in parts if part), 500)


def _overall_status(sections: list) -> str:
    statuses = {section.fact_check_status for section in sections}
    if "reject" in statuses:
        return "reject"
    if "warning" in statuses:
        return "warning"
    if statuses == {"pass"}:
        return "pass"
    return "pending"


def _compact(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "..."


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
