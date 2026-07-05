from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from api.auth import verify_api_key
from api.db import require_engine
from api.models.notices import (
    CommonUploadListResponse,
    CommonUploadResponse,
    HwpAgentHealthResponse,
    HwpTemplateFieldMapping,
    HwpTemplateListResponse,
    HwpTemplateRecord,
)
from api.services.hwp_agent_client import HwpAgentClient
from api.services.uploads import (
    analyze_upload,
    build_metadata,
    list_common_uploads,
    save_common_upload,
    save_stream,
)
from api.tables import document_field_mappings, hwp_templates

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


@router.get("/hwp-templates", response_model=HwpTemplateListResponse)
def list_hwp_templates() -> HwpTemplateListResponse:
    engine = require_engine()
    with engine.begin() as conn:
        templates = [
            dict(row)
            for row in conn.execute(
                hwp_templates.select()
                .where(hwp_templates.c.active.is_(True))
                .order_by(hwp_templates.c.template_key)
            ).mappings()
        ]
        mappings_by_template: dict[int, list[dict]] = {int(item["id"]): [] for item in templates}
        if templates:
            rows = conn.execute(
                document_field_mappings.select()
                .where(
                    document_field_mappings.c.template_id.in_(mappings_by_template.keys()),
                    document_field_mappings.c.active.is_(True),
                )
                .order_by(
                    document_field_mappings.c.template_id,
                    document_field_mappings.c.sort_order,
                    document_field_mappings.c.id,
                )
            ).mappings()
            for row in rows:
                mappings_by_template[int(row["template_id"])].append(dict(row))
    return HwpTemplateListResponse(
        items=[
            HwpTemplateRecord(
                id=int(template["id"]),
                template_key=str(template["template_key"]),
                kind=template["kind"],
                name=str(template["name"]),
                template_path=str(template["template_path"]),
                template_version=template.get("template_version"),
                active=bool(template.get("active", True)),
                mappings=[
                    HwpTemplateFieldMapping(
                        id=item.get("id"),
                        hwp_field_name=str(item.get("hwp_field_name") or ""),
                        context_path=str(item.get("context_path") or ""),
                        value_type=str(item.get("value_type") or "string"),
                        required=bool(item.get("required")),
                        default_value=item.get("default_value"),
                        transform=str(item.get("transform") or "none"),
                        sort_order=int(item.get("sort_order") or 0),
                        active=bool(item.get("active", True)),
                    )
                    for item in mappings_by_template.get(int(template["id"]), [])
                ],
            )
            for template in templates
        ]
    )


@router.get("/hwp-agent/health", response_model=HwpAgentHealthResponse)
def hwp_agent_health() -> HwpAgentHealthResponse:
    client = HwpAgentClient()
    ok = client.health()
    return HwpAgentHealthResponse(
        ok=ok,
        base_url=client.base_url,
        detail=None if ok else "milim-hwp-agent is not reachable or returned unhealthy status",
    )
