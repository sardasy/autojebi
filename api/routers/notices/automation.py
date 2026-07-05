"""서류 자동화 — 요구서류 분석 / 체크리스트 수정 / 제출 준비 검증."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, update

from api.db import require_engine
from api.models.notices import (
    ChecklistUpdateRequest,
    DocumentAutomationResponse,
    DocumentAutomationResult,
    DocumentValidationResponse,
)
from api.services.document_automation import (
    analyze_document_requirements,
    update_checklist_item,
    validate_document_automation,
)
from api.services.status import advance_status
from api.tables import bid_pipeline

from ._common import _record_errors

router = APIRouter()


@router.post("/{notice_no}/documents/analyze", response_model=DocumentAutomationResponse)
def analyze_documents(notice_no: str) -> DocumentAutomationResponse:
    engine = require_engine()

    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")
        if row["status"] not in {
            "analyzed",
            "attachments_fetched",
            "documents_analyzed",
            "spec_extracted",
            "hwp_composed",
            "form_filled",
        }:
            raise HTTPException(
                status_code=409,
                detail=f"documents can be analyzed only after notice analysis (current: {row['status']})",
            )

        merged_analysis = dict(row["analysis"] or {})
        previous_docs = merged_analysis.get("document_automation")
        document_automation = analyze_document_requirements(row)
        new_errors = list(document_automation.get("errors") or [])
        if isinstance(previous_docs, dict):
            for key in ("uploads", "exports"):
                if previous_docs.get(key):
                    document_automation[key] = list(previous_docs.get(key) or [])
            if previous_docs.get("errors"):
                document_automation["errors"] = list(previous_docs.get("errors") or []) + list(
                    document_automation.get("errors") or []
                )
        _record_errors(conn, notice_no, new_errors)
        merged_analysis["document_automation"] = document_automation
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(
                analysis=merged_analysis,
                status=advance_status(row["status"], "documents_analyzed"),
            )
        )
        return DocumentAutomationResponse(
            notice_no=notice_no,
            document_automation=DocumentAutomationResult.model_validate(document_automation),
        )


@router.patch(
    "/{notice_no}/documents/checklist/{item_id}",
    response_model=DocumentAutomationResponse,
)
def patch_document_checklist_item(
    notice_no: str,
    item_id: str,
    body: ChecklistUpdateRequest,
) -> DocumentAutomationResponse:
    engine = require_engine()

    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")
        analysis = dict(row["analysis"] or {})
        document_automation = analysis.get("document_automation")
        if not isinstance(document_automation, dict):
            raise HTTPException(status_code=409, detail="document automation has not been analyzed")
        try:
            updated_docs = update_checklist_item(
                document_automation,
                item_id,
                status=body.status,
                owner=body.owner,
                note=body.note,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="checklist item not found")

        analysis["document_automation"] = updated_docs
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(analysis=analysis)
        )
        return DocumentAutomationResponse(
            notice_no=notice_no,
            document_automation=DocumentAutomationResult.model_validate(updated_docs),
        )


@router.post("/{notice_no}/documents/validate", response_model=DocumentValidationResponse)
def validate_documents(notice_no: str) -> DocumentValidationResponse:
    engine = require_engine()

    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")
        analysis = dict(row["analysis"] or {})
        document_automation = analysis.get("document_automation")
        if not isinstance(document_automation, dict):
            raise HTTPException(status_code=409, detail="document automation has not been analyzed")

        updated_docs = validate_document_automation(document_automation)
        analysis["document_automation"] = updated_docs
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(analysis=analysis)
        )
        result = DocumentAutomationResult.model_validate(updated_docs)
        return DocumentValidationResponse(
            notice_no=notice_no,
            ready_for_submission=result.ready_for_submission,
            missing_required=result.missing_required,
            checklist=result.checklist,
        )
