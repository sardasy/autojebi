"""스펙 항목 — 추출 / 목록 / 개별 수정."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, update

from api.db import Conn, require_engine
from api.models.notices import (
    NoticeSpecItem,
    SpecItemExtractResponse,
    SpecItemListResponse,
    SpecItemUpdateRequest,
)
from api.services.spec_items import (
    build_spec_item_candidates,
    merge_candidate_with_existing,
    spec_items_to_elec_spec,
)
from api.services.status import advance_status
from api.tables import bid_pipeline, notice_spec_items

from ._common import (
    _list_spec_item_rows,
    _replace_technical_draft_from_spec_items,
    require_notice,
)

router = APIRouter()


def _spec_item_to_model(row: Any) -> NoticeSpecItem:
    return NoticeSpecItem(
        id=int(row["id"]),
        notice_no=str(row["notice_no"]),
        item_key=str(row["item_key"]),
        label=str(row["label"]),
        required_value=row.get("required_value"),
        proposed_value=row.get("proposed_value"),
        unit=row.get("unit"),
        category=str(row.get("category") or "technical"),
        source=str(row.get("source") or "rule"),
        confidence=float(row.get("confidence") or 0),
        evidence=dict(row.get("evidence") or {}),
        status=row.get("status") or "candidate",
        sort_order=int(row.get("sort_order") or 0),
        note=row.get("note"),
        reviewed_by=row.get("reviewed_by"),
        reviewed_at=row.get("reviewed_at"),
        locked_fields=list(row.get("locked_fields") or []),
        source_text=row.get("source_text"),
        source_file_name=row.get("source_file_name"),
        source_page=row.get("source_page"),
        review_priority=row.get("review_priority") or "normal",
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


@router.post("/{notice_no}/spec-items/extract", response_model=SpecItemExtractResponse)
def extract_spec_items(notice_no: str) -> SpecItemExtractResponse:
    engine = require_engine()
    with engine.begin() as conn:
        row = require_notice(conn, notice_no)

        existing_rows = {
            item["item_key"]: item
            for item in _list_spec_item_rows(conn, notice_no)
            if item.get("item_key")
        }
        upserted = 0
        for candidate in build_spec_item_candidates(row):
            merged = merge_candidate_with_existing(
                candidate,
                existing_rows.get(candidate["item_key"]),
            )
            values = {
                "notice_no": notice_no,
                "item_key": merged["item_key"],
                "label": merged["label"],
                "required_value": merged.get("required_value") or None,
                "proposed_value": merged.get("proposed_value") or None,
                "unit": merged.get("unit") or None,
                "category": merged.get("category") or "technical",
                "source": merged.get("source") or "rule",
                "confidence": merged.get("confidence") or 0,
                "evidence": merged.get("evidence") or {},
                "status": merged.get("status") or "candidate",
                "sort_order": merged.get("sort_order") or 0,
                "note": merged.get("note"),
                "reviewed_by": merged.get("reviewed_by"),
                "reviewed_at": merged.get("reviewed_at"),
                "locked_fields": merged.get("locked_fields") or [],
                "source_text": merged.get("source_text"),
                "source_file_name": merged.get("source_file_name"),
                "source_page": merged.get("source_page"),
                "review_priority": merged.get("review_priority") or "normal",
                "updated_at": datetime.now(tz=UTC),
            }
            if merged.get("id"):
                conn.execute(
                    update(notice_spec_items)
                    .where(notice_spec_items.c.id == merged["id"])
                    .values(**values)
                )
            else:
                conn.execute(notice_spec_items.insert().values(**values))
            upserted += 1

        rows = _list_spec_item_rows(conn, notice_no)
        analysis = dict(row["analysis"] or {})
        analysis["elec_spec"] = spec_items_to_elec_spec(
            rows,
            dict(analysis.get("elec_spec") or {}),
        )
        docs = analysis.get("document_automation")
        if isinstance(docs, dict):
            analysis["document_automation"] = _replace_technical_draft_from_spec_items(docs, rows)
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(
                analysis=analysis,
                status=advance_status(row["status"], "spec_extracted"),
            )
        )

        return SpecItemExtractResponse(
            notice_no=notice_no,
            items=[_spec_item_to_model(item) for item in rows],
            upserted=upserted,
        )


@router.get("/{notice_no}/spec-items", response_model=SpecItemListResponse)
def list_spec_items(notice_no: str, conn: Conn) -> SpecItemListResponse:
    require_notice(conn, notice_no, columns=[bid_pipeline.c.notice_no])
    rows = _list_spec_item_rows(conn, notice_no)
    return SpecItemListResponse(
        notice_no=notice_no,
        items=[_spec_item_to_model(item) for item in rows],
    )


@router.patch("/{notice_no}/spec-items/{item_id}", response_model=NoticeSpecItem)
def patch_spec_item(
    notice_no: str,
    item_id: int,
    body: SpecItemUpdateRequest,
) -> NoticeSpecItem:
    engine = require_engine()
    with engine.begin() as conn:
        current = conn.execute(
            select(notice_spec_items).where(
                notice_spec_items.c.notice_no == notice_no,
                notice_spec_items.c.id == item_id,
            )
        ).mappings().one_or_none()
        if not current:
            raise HTTPException(status_code=404, detail="spec item not found")
        values = {
            key: value
            for key, value in body.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if values:
            now = datetime.now(tz=UTC)
            values["updated_at"] = now
            if "source" not in values:
                values["source"] = "manual"
            next_status = values.get("status") or current.get("status")
            if next_status in {"reviewed", "matched"}:
                values.setdefault("reviewed_by", "manual")
                values.setdefault("reviewed_at", now)
            conn.execute(
                update(notice_spec_items)
                .where(notice_spec_items.c.id == item_id)
                .values(**values)
            )
        updated = conn.execute(
            select(notice_spec_items).where(notice_spec_items.c.id == item_id)
        ).mappings().one()

        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if row:
            rows = _list_spec_item_rows(conn, notice_no)
            analysis = dict(row["analysis"] or {})
            analysis["elec_spec"] = spec_items_to_elec_spec(
                rows,
                dict(analysis.get("elec_spec") or {}),
            )
            docs = analysis.get("document_automation")
            if isinstance(docs, dict):
                analysis["document_automation"] = _replace_technical_draft_from_spec_items(docs, rows)
            conn.execute(
                update(bid_pipeline)
                .where(bid_pipeline.c.notice_no == notice_no)
                .values(analysis=analysis)
            )
        return _spec_item_to_model(dict(updated))
