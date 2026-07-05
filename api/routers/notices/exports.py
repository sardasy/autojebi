"""서류 내보내기 — Excel/HWP export 생성 및 다운로드."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from api.db import require_engine
from api.models.notices import (
    ExportCreateRequest,
    ExportKind,
    ExportResponse,
)
from api.services.document_automation import validate_pre_compose
from api.services.exporters import (
    build_excel,
    build_hwp,
    get_technical_compliance_draft,
    lookup_export,
    merge_export_into_document_automation,
)
from api.tables import notice_exports

from . import _common
from ._common import (
    _list_required_document_rows,
    _list_spec_item_rows,
    _load_document_automation,
    _persist_document_automation,
    _record_errors,
    _record_export,
)

router = APIRouter()


def _lookup_active_export(conn, notice_no: str, *, kind: str, draft_id: str) -> dict | None:
    row = conn.execute(
        select(notice_exports)
        .where(
            notice_exports.c.notice_no == notice_no,
            notice_exports.c.kind == kind,
            notice_exports.c.draft_id == draft_id,
            notice_exports.c.deleted_at.is_(None),
        )
        .order_by(notice_exports.c.created_at.desc(), notice_exports.c.id.desc())
        .limit(1)
    ).mappings().first()
    if not row:
        return None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "draft_id": row["draft_id"],
        "output_path": row["output_path"],
        "mime": row["mime"],
        "generated_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
        "notes": row["notes"],
        "version": row["version"],
        "template_version": row["template_version"],
        "validation_status": row["validation_status"],
        "validation_errors": row["validation_errors"] or [],
        "file_size": row["file_size"],
        "sha256": row["sha256"],
    }


def _lookup_export_by_id(conn, notice_no: str, export_id: int) -> dict | None:
    row = conn.execute(
        select(notice_exports)
        .where(
            notice_exports.c.id == export_id,
            notice_exports.c.notice_no == notice_no,
            notice_exports.c.deleted_at.is_(None),
        )
        .limit(1)
    ).mappings().first()
    if not row:
        return None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "draft_id": row["draft_id"],
        "output_path": row["output_path"],
        "mime": row["mime"],
        "generated_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
        "notes": row["notes"],
        "version": row["version"],
        "template_version": row["template_version"],
        "validation_status": row["validation_status"],
        "validation_errors": row["validation_errors"] or [],
        "file_size": row["file_size"],
        "sha256": row["sha256"],
    }


@router.post("/{notice_no}/documents/exports/{kind}", response_model=ExportResponse)
def export_document(
    notice_no: str,
    kind: ExportKind,
    body: ExportCreateRequest | None = Body(default=None),
) -> ExportResponse:
    engine = require_engine()
    validation_failure: list[dict[str, Any]] | None = None
    response: ExportResponse | None = None
    with engine.begin() as conn:
        row, analysis, document_automation = _load_document_automation(conn, notice_no)
        draft = get_technical_compliance_draft(document_automation)
        title = str(row["title"] or notice_no)
        if kind == "proposal_hwp":
            raise HTTPException(status_code=400, detail=f"unsupported export kind: {kind}")
        spec_rows = _list_spec_item_rows(conn, notice_no, include_ignored=False)
        pre_errors, pre_warnings = validate_pre_compose(
            document_automation,
            spec_rows=spec_rows,
            required_docs=_list_required_document_rows(conn, notice_no),
            values={},
            target_item_ids={"technical_compliance"},
        )
        if kind == "hwp" and pre_errors:
            updated_docs = dict(document_automation)
            updated_docs["errors"] = list(updated_docs.get("errors") or []) + pre_errors
            _record_errors(conn, notice_no, pre_errors)
            _persist_document_automation(conn, notice_no, analysis, updated_docs)
            validation_failure = pre_errors
        elif kind == "excel":
            export = build_excel(
                notice_no=notice_no,
                draft=draft,
                title=title,
                version=(body.version if body else "compliance_excel_v2"),
                notice_meta={
                    "org_name": row.get("org_name") or "",
                    "status": row.get("status") or "",
                },
                validation_warnings=pre_warnings,
            )
        elif kind == "hwp":
            export = build_hwp(
                client=_common._make_hwp_agent_client(),
                notice_no=notice_no,
                draft=draft,
                title=title,
            )
            if pre_warnings:
                export = export.model_copy(
                    update={"validation_status": "warning", "validation_errors": pre_warnings}
                )
        else:
            raise HTTPException(status_code=400, detail=f"unsupported export kind: {kind}")
        if validation_failure:
            response = None
        else:
            export = _record_export(conn, notice_no, export)
            updated_docs = merge_export_into_document_automation(document_automation, export)
            _persist_document_automation(conn, notice_no, analysis, updated_docs)
            response = ExportResponse(notice_no=notice_no, export=export)
    if validation_failure:
        raise HTTPException(
            status_code=409,
            detail={"message": "pre-compose validation failed", "errors": validation_failure},
        )
    assert response is not None
    return response


def _export_file_response(notice_no: str, meta: dict[str, Any]) -> FileResponse:
    kind = str(meta.get("kind") or "")
    output_path = str(meta.get("output_path") or "")
    if not output_path:
        raise HTTPException(status_code=404, detail="export output path missing")
    if not os.path.isfile(output_path):
        raise HTTPException(status_code=410, detail="export file missing on disk")
    suffix = "xlsx" if kind == "excel" else "hwp"
    name = "proposal" if kind == "proposal_hwp" else "bid-form" if kind == "bid_form_hwp" else "compliance"
    return FileResponse(
        output_path,
        media_type=str(meta.get("mime") or "application/octet-stream"),
        filename=f"{notice_no}-{name}.{suffix}",
    )


@router.get("/{notice_no}/documents/exports/by-id/{export_id}/download")
def download_document_export_by_id(notice_no: str, export_id: int) -> FileResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _load_document_automation(conn, notice_no)
        meta = _lookup_export_by_id(conn, notice_no, export_id)
        if not meta:
            raise HTTPException(status_code=404, detail="export not found")
        return _export_file_response(notice_no, meta)


@router.get("/{notice_no}/documents/exports/{kind}/download")
def download_document_export(notice_no: str, kind: ExportKind) -> FileResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _, _, document_automation = _load_document_automation(conn, notice_no)
        draft_id = "proposal" if kind == "proposal_hwp" else "technical_compliance"
        meta = _lookup_active_export(conn, notice_no, kind=kind, draft_id=draft_id)
        if not meta:
            meta = lookup_export(document_automation, kind=kind, draft_id=draft_id)
        if not meta:
            raise HTTPException(
                status_code=404,
                detail=f"export not generated yet — POST /notices/{notice_no}/documents/exports/{kind} first",
            )
        return _export_file_response(notice_no, meta)
