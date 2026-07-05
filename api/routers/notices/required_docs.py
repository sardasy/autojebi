"""필요서류 자동확인 (notice_required_documents) — 추출/분류/목록/수정."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, update

from api.db import require_engine
from api.llm.extractor import extract_pdf_pages
from api.models.notices import (
    NoticeRequiredDocument,
    RequiredDocumentAnalyzeResponse,
    RequiredDocumentDiagnostics,
    RequiredDocumentListResponse,
    RequiredDocumentUpdateRequest,
)
from api.services.required_documents import (
    classify_required_documents,
    find_candidate_segments,
)
from api.tables import bid_pipeline, notice_required_documents

from . import _common
from ._common import _list_required_document_rows

router = APIRouter()


def _required_doc_to_model(row: dict[str, Any]) -> NoticeRequiredDocument:
    return NoticeRequiredDocument(
        id=int(row["id"]),
        notice_no=str(row["notice_no"]),
        doc_name=str(row["doc_name"]),
        requirement_type=str(row.get("requirement_type") or "required"),
        submit_stage=str(row.get("submit_stage") or "bid"),
        source_file=row.get("source_file"),
        evidence_text=row.get("evidence_text"),
        page_no=row.get("page_no"),
        deadline=row.get("deadline"),
        condition=row.get("condition"),
        confidence=float(row.get("confidence") or 0.0),
        checked=bool(row.get("checked")),
        owner=row.get("owner"),
        note=row.get("note"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _extract_file_pages(uploads: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """업로드(첨부)들의 storage_path에서 페이지단위 텍스트를 온디맨드 추출."""
    file_pages: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    hwp_client = _common._make_hwp_agent_client()
    hwp_ok: bool | None = None
    for up in uploads:
        if not isinstance(up, dict):
            continue
        name = str(up.get("name") or "첨부")
        storage_path = up.get("storage_path")
        mime = str(up.get("mime") or "").lower()
        lower = name.lower()
        try:
            if storage_path and Path(storage_path).exists() and (lower.endswith(".pdf") or "pdf" in mime):
                for pg in extract_pdf_pages(Path(storage_path).read_bytes()):
                    file_pages.append(
                        {"source_file": name, "page_no": pg["page_no"], "text": pg["text"]}
                    )
            elif storage_path and Path(storage_path).exists() and (lower.endswith((".hwp", ".hwpx")) or "hwp" in mime):
                if hwp_ok is None:
                    hwp_ok = hwp_client.health()
                if hwp_ok:
                    body = hwp_client.analyze_document(str(storage_path))
                    text = str(body.get("text") or body.get("text_preview") or "")
                    if text:
                        file_pages.append({"source_file": name, "page_no": None, "text": text})
                else:
                    excerpt = up.get("text_excerpt")
                    if excerpt:
                        file_pages.append({"source_file": name, "page_no": None, "text": str(excerpt)})
            else:
                excerpt = up.get("text_excerpt")
                if excerpt:
                    file_pages.append({"source_file": name, "page_no": None, "text": str(excerpt)})
        except Exception as exc:  # noqa: BLE001
            errors.append({"stage": "extract", "file_name": name, "detail": str(exc)})
    return file_pages, errors


@router.post(
    "/{notice_no}/required-documents/analyze",
    response_model=RequiredDocumentAnalyzeResponse,
)
def analyze_required_documents(notice_no: str) -> RequiredDocumentAnalyzeResponse:
    engine = require_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")
        analysis = dict(row["analysis"] or {})
        docs = analysis.get("document_automation")
        uploads = list(docs.get("uploads") or []) if isinstance(docs, dict) else []

        file_pages, errors = _extract_file_pages(uploads)
        candidates = find_candidate_segments(file_pages)
        classified = classify_required_documents(candidates)

        # 진단: 파이프라인이 어디서 0건으로 멈췄는지
        total_chars = sum(len(str(fp.get("text") or "")) for fp in file_pages)
        files_extracted = len({fp.get("source_file") for fp in file_pages})
        if not uploads:
            stopped_at = "no_uploads"
        elif total_chars == 0:
            stopped_at = "no_text"
        elif not candidates:
            stopped_at = "no_candidates"
        elif not classified:
            stopped_at = "no_classification"
        else:
            stopped_at = "ok"
        diagnostics = RequiredDocumentDiagnostics(
            uploads=len(uploads),
            files_extracted=files_extracted,
            total_chars=total_chars,
            candidates=len(candidates),
            classified=len(classified),
            stopped_at=stopped_at,
        )

        upserted = 0
        now = datetime.now(tz=UTC)
        for item in classified:
            existing = conn.execute(
                select(notice_required_documents.c.id).where(
                    notice_required_documents.c.notice_no == notice_no,
                    notice_required_documents.c.doc_name == item["doc_name"],
                    notice_required_documents.c.submit_stage == item["submit_stage"],
                )
            ).scalar_one_or_none()
            if existing:
                # 추출 필드만 갱신 — 사람이 만진 checked/owner/note는 보존
                conn.execute(
                    update(notice_required_documents)
                    .where(notice_required_documents.c.id == existing)
                    .values(
                        requirement_type=item["requirement_type"],
                        source_file=item.get("source_file"),
                        evidence_text=item.get("evidence_text"),
                        page_no=item.get("page_no"),
                        deadline=item.get("deadline"),
                        condition=item.get("condition"),
                        confidence=item["confidence"],
                        updated_at=now,
                    )
                )
            else:
                conn.execute(
                    notice_required_documents.insert().values(
                        notice_no=notice_no,
                        doc_name=item["doc_name"],
                        requirement_type=item["requirement_type"],
                        submit_stage=item["submit_stage"],
                        source_file=item.get("source_file"),
                        evidence_text=item.get("evidence_text"),
                        page_no=item.get("page_no"),
                        deadline=item.get("deadline"),
                        condition=item.get("condition"),
                        confidence=item["confidence"],
                        created_at=now,
                        updated_at=now,
                    )
                )
                upserted += 1

        # 진단 결과를 analysis.document_automation.required_docs_meta에 영속화
        # (GET 목록에서 0건 멈춤 지점을 다시 보여주기 위함)
        if isinstance(docs, dict):
            updated_docs = dict(docs)
            updated_docs["required_docs_meta"] = diagnostics.model_dump()
            analysis["document_automation"] = updated_docs
            conn.execute(
                update(bid_pipeline)
                .where(bid_pipeline.c.notice_no == notice_no)
                .values(analysis=analysis)
            )

        rows = _list_required_document_rows(conn, notice_no)
        return RequiredDocumentAnalyzeResponse(
            notice_no=notice_no,
            items=[_required_doc_to_model(r) for r in rows],
            upserted=upserted,
            diagnostics=diagnostics,
            errors=errors,
        )


@router.get(
    "/{notice_no}/required-documents",
    response_model=RequiredDocumentListResponse,
)
def list_required_documents(notice_no: str) -> RequiredDocumentListResponse:
    engine = require_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")
        rows = _list_required_document_rows(conn, notice_no)
        meta = None
        docs = (dict(row["analysis"] or {})).get("document_automation")
        if isinstance(docs, dict) and isinstance(docs.get("required_docs_meta"), dict):
            try:
                meta = RequiredDocumentDiagnostics(**docs["required_docs_meta"])
            except Exception:  # noqa: BLE001
                meta = None
        return RequiredDocumentListResponse(
            notice_no=notice_no,
            items=[_required_doc_to_model(r) for r in rows],
            diagnostics=meta,
        )


@router.patch(
    "/{notice_no}/required-documents/{doc_id}",
    response_model=NoticeRequiredDocument,
)
def patch_required_document(
    notice_no: str,
    doc_id: int,
    body: RequiredDocumentUpdateRequest,
) -> NoticeRequiredDocument:
    engine = require_engine()
    with engine.begin() as conn:
        current = conn.execute(
            select(notice_required_documents).where(
                notice_required_documents.c.notice_no == notice_no,
                notice_required_documents.c.id == doc_id,
            )
        ).mappings().one_or_none()
        if not current:
            raise HTTPException(status_code=404, detail="required document not found")
        values = {
            key: value
            for key, value in body.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if values:
            values["updated_at"] = datetime.now(tz=UTC)
            conn.execute(
                update(notice_required_documents)
                .where(notice_required_documents.c.id == doc_id)
                .values(**values)
            )
        updated = conn.execute(
            select(notice_required_documents).where(notice_required_documents.c.id == doc_id)
        ).mappings().one()
        return _required_doc_to_model(dict(updated))
