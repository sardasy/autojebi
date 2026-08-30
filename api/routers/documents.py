from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select, update

from api.auth import verify_api_key
from api.db import require_engine
from api.models.notices import (
    CommonUploadListResponse,
    CommonUploadResponse,
    HwpAgentHealthResponse,
    HwpMappingUpdateRequest,
    HwpMappingUpsertRequest,
    HwpTemplateFieldMapping,
    HwpTemplateListResponse,
    HwpTemplateRecord,
    HwpTemplateUpdateRequest,
    HwpTemplateUpsertRequest,
)
from api.routers.notices import document_field_mappings, hwp_templates
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
            _template_record(template, mappings_by_template.get(int(template["id"]), []))
            for template in templates
        ]
    )


@router.post("/hwp-templates", response_model=HwpTemplateRecord)
def upsert_hwp_template(body: HwpTemplateUpsertRequest) -> HwpTemplateRecord:
    engine = require_engine()
    now = datetime.now(tz=UTC)
    values = body.model_dump()
    values["updated_at"] = now
    with engine.begin() as conn:
        existing = conn.execute(
            select(hwp_templates.c.id).where(hwp_templates.c.template_key == body.template_key)
        ).scalar_one_or_none()
        if existing is None:
            result = conn.execute(
                hwp_templates.insert().values(**values, created_at=now)
            )
            template_id = int(result.inserted_primary_key[0])
        else:
            template_id = int(existing)
            conn.execute(
                update(hwp_templates)
                .where(hwp_templates.c.id == template_id)
                .values(**values)
            )
        return _load_hwp_template(conn, template_id, include_inactive_template=True)


@router.patch("/hwp-templates/{template_id}", response_model=HwpTemplateRecord)
def update_hwp_template(
    template_id: int,
    body: HwpTemplateUpdateRequest,
) -> HwpTemplateRecord:
    engine = require_engine()
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="no fields to update")
    values["updated_at"] = datetime.now(tz=UTC)
    with engine.begin() as conn:
        result = conn.execute(
            update(hwp_templates)
            .where(hwp_templates.c.id == template_id)
            .values(**values)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="hwp template not found")
        return _load_hwp_template(conn, template_id, include_inactive_template=True)


@router.post("/hwp-templates/{template_id}/mappings", response_model=HwpTemplateRecord)
def upsert_hwp_mapping(
    template_id: int,
    body: HwpMappingUpsertRequest,
) -> HwpTemplateRecord:
    engine = require_engine()
    now = datetime.now(tz=UTC)
    values = body.model_dump()
    values["template_id"] = template_id
    values["updated_at"] = now
    with engine.begin() as conn:
        _ensure_template_exists(conn, template_id)
        existing = conn.execute(
            select(document_field_mappings.c.id).where(
                document_field_mappings.c.template_id == template_id,
                document_field_mappings.c.hwp_field_name == body.hwp_field_name,
            )
        ).scalar_one_or_none()
        if existing is None:
            conn.execute(document_field_mappings.insert().values(**values, created_at=now))
        else:
            conn.execute(
                update(document_field_mappings)
                .where(document_field_mappings.c.id == int(existing))
                .values(**values)
            )
        return _load_hwp_template(conn, template_id, include_inactive_template=True)


@router.patch("/hwp-templates/{template_id}/mappings/{mapping_id}", response_model=HwpTemplateRecord)
def update_hwp_mapping(
    template_id: int,
    mapping_id: int,
    body: HwpMappingUpdateRequest,
) -> HwpTemplateRecord:
    engine = require_engine()
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="no fields to update")
    values["updated_at"] = datetime.now(tz=UTC)
    with engine.begin() as conn:
        _ensure_template_exists(conn, template_id)
        result = conn.execute(
            update(document_field_mappings)
            .where(
                document_field_mappings.c.id == mapping_id,
                document_field_mappings.c.template_id == template_id,
            )
            .values(**values)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="hwp field mapping not found")
        return _load_hwp_template(conn, template_id, include_inactive_template=True)


@router.get("/hwp-agent/health", response_model=HwpAgentHealthResponse)
def hwp_agent_health() -> HwpAgentHealthResponse:
    client = HwpAgentClient()
    ok = client.health()
    return HwpAgentHealthResponse(
        ok=ok,
        base_url=client.base_url,
        detail=None if ok else "milim-hwp-agent is not reachable or returned unhealthy status",
    )


def _ensure_template_exists(conn, template_id: int) -> None:
    exists = conn.execute(
        select(hwp_templates.c.id).where(hwp_templates.c.id == template_id)
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="hwp template not found")


def _load_hwp_template(conn, template_id: int, *, include_inactive_template: bool = False) -> HwpTemplateRecord:
    conditions = [hwp_templates.c.id == template_id]
    if not include_inactive_template:
        conditions.append(hwp_templates.c.active.is_(True))
    template = conn.execute(select(hwp_templates).where(*conditions)).mappings().one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="hwp template not found")
    mappings = [
        dict(row)
        for row in conn.execute(
            select(document_field_mappings)
            .where(
                document_field_mappings.c.template_id == template_id,
                document_field_mappings.c.active.is_(True),
            )
            .order_by(document_field_mappings.c.sort_order, document_field_mappings.c.id)
        ).mappings()
    ]
    return _template_record(dict(template), mappings)


def _template_record(template: dict[str, Any], mappings: list[dict[str, Any]]) -> HwpTemplateRecord:
    return HwpTemplateRecord(
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
                transform=item.get("transform") or "none",
                sort_order=int(item.get("sort_order") or 0),
                active=bool(item.get("active", True)),
            )
            for item in mappings
        ],
    )
