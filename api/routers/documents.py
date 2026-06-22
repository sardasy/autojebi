from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from api.auth import verify_api_key
from api.models.notices import (
    CommonUploadListResponse,
    CommonUploadResponse,
    HwpAgentHealthResponse,
)
from api.services.hwp_agent_client import HwpAgentClient
from api.services.uploads import (
    analyze_upload,
    build_metadata,
    list_common_uploads,
    save_common_upload,
    save_stream,
)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/common/uploads", response_model=CommonUploadResponse)
async def upload_common_document(
    file: UploadFile = File(...),
    item_id: str | None = Form(default=None),
) -> CommonUploadResponse:
    saved = save_stream(
        file.file,
        notice_no="common",
        original_name=file.filename or "upload.bin",
    )
    analysis_meta = analyze_upload(
        saved=saved,
        original_name=file.filename or "upload.bin",
        checklist=None,
        explicit_item_id=item_id,
    )
    resolved_item_id = str(analysis_meta.pop("item_id") or "") or None
    uploaded = build_metadata(
        saved,
        original_name=file.filename or "upload.bin",
        mime=file.content_type,
        item_id=resolved_item_id,
        **analysis_meta,
    )
    save_common_upload(uploaded)
    return CommonUploadResponse(uploaded=uploaded)


@router.get("/common/uploads", response_model=CommonUploadListResponse)
def list_common_documents() -> CommonUploadListResponse:
    return CommonUploadListResponse(items=list_common_uploads())


@router.get("/hwp-agent/health", response_model=HwpAgentHealthResponse)
def hwp_agent_health() -> HwpAgentHealthResponse:
    client = HwpAgentClient()
    ok = client.health()
    return HwpAgentHealthResponse(
        ok=ok,
        base_url=client.base_url,
        detail=None if ok else "milim-hwp-agent is not reachable or returned unhealthy status",
    )
