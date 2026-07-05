"""서류 업로드 — 파일 업로드 / 공용서류 가져오기 / 목록 / 삭제 / 다운로드."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.db import Conn, require_engine
from api.models.notices import (
    UploadedDocument,
    UploadListResponse,
    UploadResponse,
)
from api.services.uploads import (
    analyze_upload,
    build_metadata,
    clone_common_upload_for_notice,
    delete_file,
    get_common_upload,
    merge_into_document_automation,
    remove_from_document_automation,
    save_stream,
)

from . import _common
from ._common import _load_document_automation, _persist_document_automation

router = APIRouter()


@router.post("/{notice_no}/documents/uploads", response_model=UploadResponse)
async def upload_document(
    notice_no: str,
    file: UploadFile = File(...),
    item_id: str | None = Form(default=None),
) -> UploadResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _, analysis, document_automation = _load_document_automation(conn, notice_no)

        saved = save_stream(
            file.file,
            notice_no=notice_no,
            original_name=file.filename or "upload.bin",
        )
        analysis_meta = analyze_upload(
            saved=saved,
            original_name=file.filename or "upload.bin",
            checklist=list(document_automation.get("checklist") or []),
            explicit_item_id=item_id,
            hwp_client=_common._make_hwp_agent_client(),
        )
        resolved_item_id = str(analysis_meta.pop("item_id") or "") or None
        uploaded = build_metadata(
            saved,
            original_name=file.filename or "upload.bin",
            mime=file.content_type,
            item_id=resolved_item_id,
            **analysis_meta,
        )
        updated_docs = merge_into_document_automation(document_automation, uploaded)
        _persist_document_automation(conn, notice_no, analysis, updated_docs)
        return UploadResponse(notice_no=notice_no, uploaded=uploaded)


@router.post("/{notice_no}/documents/import-common/{upload_id}", response_model=UploadResponse)
def import_common_document(notice_no: str, upload_id: str) -> UploadResponse:
    common = get_common_upload(upload_id)
    if common is None:
        raise HTTPException(status_code=404, detail="common upload not found")
    engine = require_engine()
    with engine.begin() as conn:
        _, analysis, document_automation = _load_document_automation(conn, notice_no)
        imported = clone_common_upload_for_notice(common)
        updated_docs = merge_into_document_automation(document_automation, imported)
        _persist_document_automation(conn, notice_no, analysis, updated_docs)
        return UploadResponse(notice_no=notice_no, uploaded=imported)

@router.get("/{notice_no}/documents/uploads", response_model=UploadListResponse)
def list_document_uploads(notice_no: str, conn: Conn) -> UploadListResponse:
    _, _, document_automation = _load_document_automation(conn, notice_no)
    items = [
        UploadedDocument.model_validate(item)
        for item in (document_automation.get("uploads") or [])
        if isinstance(item, dict)
    ]
    return UploadListResponse(notice_no=notice_no, items=items)


@router.delete("/{notice_no}/documents/uploads/{upload_id}")
def delete_document_upload(notice_no: str, upload_id: str) -> dict[str, Any]:
    engine = require_engine()
    with engine.begin() as conn:
        _, analysis, document_automation = _load_document_automation(conn, notice_no)
        updated_docs, removed = remove_from_document_automation(document_automation, upload_id)
        if removed is None:
            raise HTTPException(status_code=404, detail="upload not found")
        if removed.get("source_ref") != "common_library":
            delete_file(str(removed.get("storage_path") or ""))
        _persist_document_automation(conn, notice_no, analysis, updated_docs)
        return {"notice_no": notice_no, "deleted": upload_id}


@router.get("/{notice_no}/documents/uploads/{upload_id}/download")
def download_document_upload(notice_no: str, upload_id: str, conn: Conn) -> FileResponse:
    _, _, document_automation = _load_document_automation(conn, notice_no)
    for item in document_automation.get("uploads") or []:
        if isinstance(item, dict) and item.get("id") == upload_id:
            storage_path = str(item.get("storage_path") or "")
            if not storage_path or not os.path.isfile(storage_path):
                raise HTTPException(status_code=410, detail="upload file missing on disk")
            return FileResponse(
                storage_path,
                media_type=str(item.get("mime") or "application/octet-stream"),
                filename=str(item.get("name") or upload_id),
            )
    raise HTTPException(status_code=404, detail="upload not found")
