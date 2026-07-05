"""HWP 문서 생성 — autofill / 필드매핑 컨텍스트 / put-fields / compose / 제안서."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, update

from api.db import require_engine
from api.models.notices import (
    AutofillFormRequest,
    AutofillFormResponse,
    ExportRecord,
    HwpComposeBidFormResult,
    HwpComposeRequest,
    HwpComposeResponse,
    HwpContextRequest,
    HwpContextResponse,
    HwpJobRecord,
    HwpJobReviewRequest,
    HwpJobReviewResponse,
    HwpPutFieldsRequest,
    HwpPutFieldsResponse,
    HwpTemplateFieldMapping,
    HwpTemplateRecord,
    ProposalComposeRequest,
    ProposalComposeResponse,
    ProposalComposeResult,
)
from api.services.document_automation import attach_bid_form_result, validate_pre_compose
from api.services.exporters import (
    HWP_MIME,
    build_hwp,
    get_technical_compliance_draft,
    merge_export_into_document_automation,
    notice_dir,
    with_file_metadata,
)
from api.services.hwp_agent_client import HwpAgentError
from api.services.hwp_fields import build_hwp_context, resolve_hwp_fields
from api.services.proposals import (
    build_proposal_export,
    build_proposal_payload,
    proposal_output_path,
)
from api.services.spec_items import compose_hwp_values
from api.services.status import advance_status, can_transition
from api.tables import (
    bid_pipeline,
    document_field_mappings,
    hwp_generation_jobs,
    hwp_templates,
)

from . import _common
from ._common import (
    _company_defaults,
    _list_required_document_rows,
    _list_spec_item_rows,
    _load_company_profile,
    _load_document_automation,
    _persist_document_automation,
    _record_errors,
    _record_export,
    _replace_technical_draft_from_spec_items,
    require_notice,
)

router = APIRouter()


@router.post("/{notice_no}/autofill-form", response_model=AutofillFormResponse)
def autofill_form(notice_no: str, body: AutofillFormRequest) -> AutofillFormResponse:
    """Drives milim-hwp-agent to autofill an HWP bid-form template.

    Transitions analyzed → form_filled. Caller-supplied `values` override
    env-derived company defaults; the agent decides which placeholders are
    still missing and rejects with 422 if any required value is blank.
    """
    engine = require_engine()

    with engine.begin() as conn:
        row = require_notice(conn, notice_no)

        if not can_transition(row["status"], "form_filled"):
            raise HTTPException(
                status_code=409,
                detail=f"invalid transition {row['status']} -> form_filled",
            )

        merged_values = {**_company_defaults(row), **body.values}

        client = _common._make_hwp_agent_client()
        try:
            outcome = client.autofill_bid_form(
                template_path=body.template_path,
                output_path=body.output_path,
                values=merged_values,
                visible=body.visible,
            )
        except HwpAgentError as exc:
            existing = dict(row["analysis"] or {})
            errors = list(existing.get("errors") or [])
            errors.append({"stage": "autofill_form", "detail": str(exc)})
            existing["errors"] = errors
            conn.execute(
                update(bid_pipeline)
                .where(bid_pipeline.c.notice_no == notice_no)
                .values(analysis=existing)
            )
            raise HTTPException(status_code=502, detail=f"hwp agent failed: {exc}")

        merged_analysis = dict(row["analysis"] or {})
        merged_analysis["bid_form"] = {
            "template_path": outcome.template_path,
            "output_path": outcome.output_path,
            "placeholders": outcome.placeholders,
            "replaced": outcome.replaced,
            "missing": outcome.missing,
            "remaining_placeholders": outcome.remaining_placeholders,
            "filled_at": datetime.now(tz=UTC).isoformat(),
        }
        merged_analysis = attach_bid_form_result(
            merged_analysis,
            template_path=outcome.template_path,
            output_path=outcome.output_path,
            replaced=outcome.replaced,
            missing=outcome.missing,
            remaining_placeholders=outcome.remaining_placeholders,
        )

        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(analysis=merged_analysis, status="form_filled")
        )

        return AutofillFormResponse(
            notice_no=notice_no,
            status="form_filled",
            template_path=outcome.template_path,
            output_path=outcome.output_path,
            replaced=outcome.replaced,
            missing=outcome.missing,
            remaining_placeholders=outcome.remaining_placeholders,
        )


@router.post("/{notice_no}/documents/hwp-context", response_model=HwpContextResponse)
def preview_hwp_context(notice_no: str, body: HwpContextRequest) -> HwpContextResponse:
    engine = require_engine()
    with engine.begin() as conn:
        row, analysis, document_automation = _load_document_automation(conn, notice_no)
        proposal = None
        if body.template_key == "proposal":
            proposal = build_proposal_payload(
                row=row,
                spec_rows=_list_spec_item_rows(conn, notice_no, include_ignored=True),
                document_automation=document_automation,
                company_values=_company_defaults(row),
                overrides=body.values_override,
            )
        template, context, input_values, required_missing = _resolve_hwp_context(
            conn,
            row=row,
            analysis=analysis,
            document_automation=document_automation,
            template_key=body.template_key,
            values_override=body.values_override,
            proposal=proposal,
        )
        return HwpContextResponse(
            notice_no=notice_no,
            template=template,
            context=context,
            input_values=input_values,
            required_missing=required_missing,
        )


@router.post("/{notice_no}/documents/hwp-put-fields", response_model=HwpPutFieldsResponse)
def put_hwp_fields(notice_no: str, body: HwpPutFieldsRequest) -> HwpPutFieldsResponse:
    engine = require_engine()
    response: HwpPutFieldsResponse | None = None
    with engine.begin() as conn:
        row, analysis, document_automation = _load_document_automation(conn, notice_no)
        proposal = None
        if body.template_key == "proposal":
            proposal = build_proposal_payload(
                row=row,
                spec_rows=_list_spec_item_rows(conn, notice_no, include_ignored=True),
                document_automation=document_automation,
                company_values=_company_defaults(row),
                overrides=body.values_override,
            )
        response = _execute_hwp_put_fields(
            conn,
            row=row,
            analysis=analysis,
            document_automation=document_automation,
            template_key=body.template_key,
            values_override=body.values_override,
            output_path=body.output_path,
            visible=body.visible,
            proposal=proposal,
        )
    assert response is not None
    return response


@router.post(
    "/{notice_no}/documents/hwp-jobs/{job_id}/review",
    response_model=HwpJobReviewResponse,
)
def review_hwp_job(
    notice_no: str,
    job_id: int,
    body: HwpJobReviewRequest,
) -> HwpJobReviewResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _load_document_automation(conn, notice_no)
        existing = conn.execute(
            select(hwp_generation_jobs).where(
                hwp_generation_jobs.c.id == job_id,
                hwp_generation_jobs.c.notice_no == notice_no,
            )
        ).mappings().one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="HWP generation job not found")
        conn.execute(
            update(hwp_generation_jobs)
            .where(hwp_generation_jobs.c.id == job_id)
            .values(
                review_status=body.review_status,
                review_note=body.review_note,
                reviewed_by=body.reviewed_by,
                reviewed_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            )
        )
        row, analysis, document_automation = _load_document_automation(conn, notice_no)
        job_row = conn.execute(
            select(hwp_generation_jobs).where(hwp_generation_jobs.c.id == job_id)
        ).mappings().one()
        job = _hwp_job_to_model(dict(job_row))
        _persist_document_automation(
            conn,
            notice_no,
            analysis,
            _merge_hwp_job_into_document_automation(document_automation, job),
        )
        return HwpJobReviewResponse(notice_no=notice_no, job=job)


def _execute_hwp_put_fields(
    conn,
    *,
    row: Any,
    analysis: dict,
    document_automation: dict,
    template_key: str,
    values_override: dict[str, str],
    output_path: str | None,
    visible: bool,
    proposal: dict[str, Any] | None = None,
) -> HwpPutFieldsResponse:
    template, context, input_values, required_missing = _resolve_hwp_context(
        conn,
        row=row,
        analysis=analysis,
        document_automation=document_automation,
        template_key=template_key,
        values_override=values_override,
        proposal=proposal,
    )
    errors = [
        {
            "stage": "hwp.required",
            "severity": "warning",
            "detail": "필수 HWP 입력값이 비어 있습니다",
            "missing": required_missing,
        }
    ] if required_missing else []
    job = _record_hwp_job(
        conn,
        notice_no=row["notice_no"],
        template_id=template.id,
        status="running",
        context_json=context,
        input_values=input_values,
        missing=required_missing,
    )
    final_output_path = output_path or _default_hwp_output_path(row["notice_no"], template_key)
    export = None
    try:
        outcome = _common._make_hwp_agent_client().put_fields(
            template_path=template.template_path,
            output_path=final_output_path,
            values=input_values,
            visible=visible,
        )
    except HwpAgentError as exc:
        job = _update_hwp_job(conn, job.id, status="failed", error_detail=str(exc))
        errors.append({"stage": "hwp.put_fields", "severity": "error", "detail": str(exc)})
        _record_errors(conn, row["notice_no"], errors)
        updated_docs = _merge_hwp_job_into_document_automation(document_automation, job)
        updated_docs["errors"] = list(updated_docs.get("errors") or []) + errors
        _persist_document_automation(conn, row["notice_no"], analysis, updated_docs)
        return HwpPutFieldsResponse(
            notice_no=row["notice_no"],
            status=row["status"],
            export=None,
            job=job,
            required_missing=required_missing,
            remaining_placeholders=[],
            errors=errors,
        )

    if outcome.remaining_placeholders:
        errors.append(
            {
                "stage": "hwp.remaining_placeholders",
                "severity": "warning",
                "detail": "HWP에 남은 placeholder가 있습니다",
                "remaining_placeholders": outcome.remaining_placeholders,
            }
        )
    export_kind = "proposal_hwp" if template.kind == "proposal" else "bid_form_hwp"
    draft_id = "proposal" if template.kind == "proposal" else "bid_form"
    if export_kind == "proposal_hwp":
        export = build_proposal_export(
            notice_no=row["notice_no"],
            output_path=outcome.output_path,
            notes="PutFieldText",
        )
        if errors:
            export = export.model_copy(update={"validation_status": "warning", "validation_errors": errors})
    else:
        export = _build_bid_form_export(output_path=outcome.output_path, validation_errors=errors)
    export = export.model_copy(update={"kind": export_kind, "draft_id": draft_id})
    export = _record_export(conn, row["notice_no"], export)
    job = _update_hwp_job(
        conn,
        job.id,
        status="completed",
        export_id=export.id,
        replaced=outcome.replaced,
        missing=list(dict.fromkeys(required_missing + outcome.missing)),
        remaining_placeholders=outcome.remaining_placeholders,
        worker_raw=outcome.raw,
    )
    updated_docs = merge_export_into_document_automation(document_automation, export)
    updated_docs = _merge_hwp_job_into_document_automation(updated_docs, job)
    updated_docs["errors"] = list(updated_docs.get("errors") or []) + errors
    if proposal:
        drafts = dict(updated_docs.get("drafts") or {})
        drafts["proposal"] = proposal
        updated_docs["drafts"] = drafts
    _record_errors(conn, row["notice_no"], errors)
    next_status = advance_status(row["status"], "hwp_composed")
    if template.kind == "bid_form" and not errors and not outcome.remaining_placeholders:
        next_status = advance_status(next_status, "form_filled")
    analysis["document_automation"] = updated_docs
    conn.execute(
        update(bid_pipeline)
        .where(bid_pipeline.c.notice_no == row["notice_no"])
        .values(analysis=analysis, status=next_status)
    )
    return HwpPutFieldsResponse(
        notice_no=row["notice_no"],
        status=next_status,
        export=export,
        job=job,
        required_missing=required_missing,
        remaining_placeholders=outcome.remaining_placeholders,
        errors=errors,
    )


def _template_to_model(template: dict[str, Any], mappings: list[dict[str, Any]]) -> HwpTemplateRecord:
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
                transform=str(item.get("transform") or "none"),
                sort_order=int(item.get("sort_order") or 0),
                active=bool(item.get("active", True)),
            )
            for item in mappings
        ],
    )


def _load_hwp_template(conn, template_key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    template = conn.execute(
        select(hwp_templates)
        .where(hwp_templates.c.template_key == template_key, hwp_templates.c.active.is_(True))
        .limit(1)
    ).mappings().one_or_none()
    if not template:
        raise HTTPException(status_code=409, detail=f"HWP template not seeded: {template_key}")
    mappings = [
        dict(row)
        for row in conn.execute(
            select(document_field_mappings)
            .where(
                document_field_mappings.c.template_id == template["id"],
                document_field_mappings.c.active.is_(True),
            )
            .order_by(document_field_mappings.c.sort_order, document_field_mappings.c.id)
        ).mappings()
    ]
    if not mappings:
        raise HTTPException(status_code=409, detail=f"HWP field mappings not seeded: {template_key}")
    return dict(template), mappings


def _proposal_context_summary(row: Any, spec_rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = compose_hwp_values(row, spec_rows, {})
    return {"values": values, **values}


def _resolve_hwp_context(
    conn,
    *,
    row: Any,
    analysis: dict,
    document_automation: dict,
    template_key: str,
    values_override: dict[str, str],
    proposal: dict[str, Any] | None = None,
) -> tuple[HwpTemplateRecord, dict[str, Any], dict[str, str], list[str]]:
    template, mappings = _load_hwp_template(conn, template_key)
    spec_rows = _list_spec_item_rows(conn, row["notice_no"], include_ignored=True)
    proposal_context = proposal or _proposal_context_summary(row, spec_rows)
    context = build_hwp_context(
        row=row,
        company=_load_company_profile(conn, row),
        spec_rows=spec_rows,
        document_automation=document_automation,
        proposal=proposal_context,
    )
    try:
        resolved = resolve_hwp_fields(
            context=context,
            mappings=mappings,
            values_override=values_override,
        )
    except ValueError as exc:
        job = _record_hwp_job(
            conn,
            notice_no=row["notice_no"],
            template_id=int(template["id"]),
            status="failed",
            context_json=context,
            input_values={},
            error_detail=str(exc),
        )
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "job_id": job.id},
        ) from exc
    return (
        _template_to_model(template, mappings),
        resolved.context,
        resolved.input_values,
        resolved.required_missing,
    )


def _record_hwp_job(
    conn,
    *,
    notice_no: str,
    template_id: int | None,
    status: str,
    context_json: dict[str, Any],
    input_values: dict[str, str],
    missing: list[str] | None = None,
    remaining_placeholders: list[str] | None = None,
    worker_raw: dict[str, Any] | None = None,
    error_detail: str | None = None,
    export_id: int | None = None,
) -> HwpJobRecord:
    result = conn.execute(
        hwp_generation_jobs.insert().values(
            notice_no=notice_no,
            template_id=template_id,
            export_id=export_id,
            status=status,
            context_json=_jsonable(context_json),
            input_values=_jsonable(input_values),
            missing=missing or [],
            remaining_placeholders=remaining_placeholders or [],
            worker_raw=_jsonable(worker_raw or {}),
            error_detail=error_detail,
            review_status="pending",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
    )
    job_id = int(result.inserted_primary_key[0])
    row = conn.execute(
        select(hwp_generation_jobs).where(hwp_generation_jobs.c.id == job_id)
    ).mappings().one()
    return _hwp_job_to_model(dict(row))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _update_hwp_job(
    conn,
    job_id: int,
    **values: Any,
) -> HwpJobRecord:
    values["updated_at"] = datetime.now(tz=UTC)
    conn.execute(
        update(hwp_generation_jobs)
        .where(hwp_generation_jobs.c.id == job_id)
        .values(**values)
    )
    row = conn.execute(
        select(hwp_generation_jobs).where(hwp_generation_jobs.c.id == job_id)
    ).mappings().one()
    return _hwp_job_to_model(dict(row))


def _hwp_job_to_model(row: dict[str, Any]) -> HwpJobRecord:
    return HwpJobRecord(
        id=int(row["id"]),
        notice_no=str(row["notice_no"]),
        template_id=row.get("template_id"),
        export_id=row.get("export_id"),
        status=str(row.get("status") or "pending"),
        input_values=dict(row.get("input_values") or {}),
        replaced=list(row.get("replaced") or []),
        missing=list(row.get("missing") or []),
        remaining_placeholders=list(row.get("remaining_placeholders") or []),
        error_detail=row.get("error_detail"),
        review_status=str(row.get("review_status") or "pending"),
        review_note=row.get("review_note"),
        reviewed_by=row.get("reviewed_by"),
    )


def _merge_hwp_job_into_document_automation(document_automation: dict, job: HwpJobRecord) -> dict:
    updated = dict(document_automation)
    jobs = [
        item
        for item in list(updated.get("hwp_jobs") or [])
        if not (isinstance(item, dict) and item.get("id") == job.id)
    ]
    jobs.insert(0, job.model_dump())
    updated["hwp_jobs"] = jobs[:10]
    return updated


def _build_bid_form_export(*, output_path: str, validation_errors: list[dict[str, Any]]) -> ExportRecord:
    return with_file_metadata(
        ExportRecord(
            kind="bid_form_hwp",
            draft_id="bid_form",
            output_path=output_path,
            mime=HWP_MIME,
            generated_at=datetime.now(tz=UTC).isoformat(),
            notes="PutFieldText",
            version="bid_form_hwp_v1",
            template_version="put_fields_v1",
            validation_status="warning" if validation_errors else "passed",
            validation_errors=validation_errors,
        )
    )


def _default_hwp_output_path(notice_no: str, template_key: str) -> str:
    safe_key = template_key.replace("/", "_")
    return str(notice_dir(notice_no) / f"{safe_key}_{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}.hwp")


@router.post("/{notice_no}/documents/hwp-compose", response_model=HwpComposeResponse)
def compose_hwp_documents(notice_no: str, body: HwpComposeRequest) -> HwpComposeResponse:
    engine = require_engine()
    validation_failure: list[dict[str, Any]] | None = None
    response: HwpComposeResponse | None = None
    with engine.begin() as conn:
        row, analysis, document_automation = _load_document_automation(conn, notice_no)
        spec_rows = _list_spec_item_rows(conn, notice_no, include_ignored=False)

        errors: list[dict[str, Any]] = []
        target_ids: set[str] = set()
        if body.include_bid_form:
            target_ids.add("bid_form")
        if body.include_technical_compliance:
            target_ids.add("technical_compliance")
        pre_errors, pre_warnings = validate_pre_compose(
            document_automation,
            spec_rows=spec_rows,
            required_docs=_list_required_document_rows(conn, notice_no),
            values=body.values,
            target_item_ids=target_ids,
        )
        if pre_errors:
            updated_docs = dict(document_automation)
            updated_docs["errors"] = list(updated_docs.get("errors") or []) + pre_errors
            _record_errors(conn, notice_no, pre_errors)
            _persist_document_automation(conn, notice_no, analysis, updated_docs)
            validation_failure = pre_errors
        if validation_failure:
            response = None
        else:
            errors.extend(pre_warnings)
        bid_result: HwpComposeBidFormResult | None = None
        hwp_job: HwpJobRecord | None = None
        required_missing: list[str] = []
        export = None
        updated_analysis = dict(analysis)
        updated_docs = _replace_technical_draft_from_spec_items(document_automation, spec_rows)
        client = _common._make_hwp_agent_client()

        if not validation_failure and body.include_bid_form:
            output_path = body.bid_form_output_path
            draft_values: dict[str, str] = {}
            drafts = updated_docs.get("drafts") if isinstance(updated_docs, dict) else None
            if isinstance(drafts, dict) and isinstance(drafts.get("bid_form_values"), dict):
                values = drafts["bid_form_values"].get("values")
                if isinstance(values, dict):
                    draft_values = {key: str(value) for key, value in values.items()}
            merged_values = {
                **draft_values,
                **body.values,
            }
            result = _execute_hwp_put_fields(
                conn,
                row=row,
                analysis=updated_analysis,
                document_automation=updated_docs,
                template_key="bid_form",
                values_override=merged_values,
                output_path=output_path,
                visible=body.visible,
            )
            hwp_job = result.job
            required_missing = result.required_missing
            errors.extend(result.errors)
            if result.job:
                updated_docs = _merge_hwp_job_into_document_automation(updated_docs, result.job)
            if result.export:
                updated_docs = merge_export_into_document_automation(updated_docs, result.export)
            if result.export:
                bid_result = HwpComposeBidFormResult(
                    template_path=body.bid_form_template_path,
                    output_path=result.export.output_path,
                    replaced=result.job.replaced,
                    missing=result.job.missing,
                    remaining_placeholders=result.remaining_placeholders,
                )

        if not validation_failure and body.include_technical_compliance:
            try:
                draft = get_technical_compliance_draft(updated_docs)
                export = build_hwp(
                    client=client,
                    notice_no=notice_no,
                    draft=draft,
                    title=str(row["title"] or notice_no),
                )
                if pre_warnings:
                    export = export.model_copy(
                        update={"validation_status": "warning", "validation_errors": pre_warnings}
                    )
                export = _record_export(conn, notice_no, export)
                updated_docs = merge_export_into_document_automation(updated_docs, export)
            except HTTPException as exc:
                errors.append({"stage": "technical_compliance", "detail": str(exc.detail)})

        if not validation_failure:
            existing_errors = list(updated_docs.get("errors") or [])
            updated_docs["errors"] = existing_errors + errors
            _record_errors(conn, notice_no, errors)
            updated_analysis["document_automation"] = updated_docs
            next_status = advance_status(row["status"], "hwp_composed") if export else row["status"]
            remaining = bid_result.remaining_placeholders if bid_result else []
            blocking_errors = [item for item in errors if item.get("severity", "error") == "error"]
            if (
                not blocking_errors
                and not remaining
                and body.include_bid_form
                and bid_result is not None
            ):
                next_status = advance_status(next_status, "form_filled")

            conn.execute(
                update(bid_pipeline)
                .where(bid_pipeline.c.notice_no == notice_no)
                .values(analysis=updated_analysis, status=next_status)
            )
            response = HwpComposeResponse(
                notice_no=notice_no,
                status=next_status,
                bid_form=bid_result,
                technical_compliance=export,
                job=hwp_job,
                required_missing=required_missing,
                remaining_placeholders=remaining,
                errors=errors,
            )
    if validation_failure:
        raise HTTPException(
            status_code=409,
            detail={"message": "pre-compose validation failed", "errors": validation_failure},
        )
    assert response is not None
    return response


@router.post("/{notice_no}/documents/proposal-compose", response_model=ProposalComposeResponse)
def compose_proposal_document(
    notice_no: str,
    body: ProposalComposeRequest,
) -> ProposalComposeResponse:
    engine = require_engine()
    validation_failure: list[dict[str, Any]] | None = None
    response: ProposalComposeResponse | None = None
    with engine.begin() as conn:
        row, analysis, document_automation = _load_document_automation(conn, notice_no)
        spec_rows = _list_spec_item_rows(conn, notice_no, include_ignored=True)
        pre_errors, pre_warnings = validate_pre_compose(
            document_automation,
            spec_rows=spec_rows,
            required_docs=_list_required_document_rows(conn, notice_no),
            values=body.values_override,
            target_item_ids={"bid_form", "technical_compliance", "proposal"},
        )
        if pre_errors:
            updated_docs = dict(document_automation)
            updated_docs["errors"] = list(updated_docs.get("errors") or []) + pre_errors
            _record_errors(conn, notice_no, pre_errors)
            _persist_document_automation(conn, notice_no, analysis, updated_docs)
            validation_failure = pre_errors
        if validation_failure:
            response = None
        else:
            errors: list[dict[str, Any]] = list(pre_warnings)

        updated_docs = dict(document_automation)
        drafts = dict(updated_docs.get("drafts") or {})
        proposal = build_proposal_payload(
            row=row,
            spec_rows=spec_rows,
            document_automation=updated_docs,
            company_values=_company_defaults(row),
            overrides=body.values_override,
        )
        drafts["proposal"] = proposal
        updated_docs["drafts"] = drafts

        export = None
        remaining: list[str] = []
        output_path = body.output_path or proposal_output_path(notice_no)
        job: HwpJobRecord | None = None
        required_missing: list[str] = []
        if not validation_failure:
            put_result = _execute_hwp_put_fields(
                conn,
                row=row,
                analysis=analysis,
                document_automation=updated_docs,
                template_key="proposal",
                values_override=body.values_override,
                output_path=output_path,
                visible=body.visible,
                proposal=proposal,
            )
            export = put_result.export
            job = put_result.job
            remaining = put_result.remaining_placeholders
            required_missing = put_result.required_missing
            errors.extend(put_result.errors)
            proposal["result"] = ProposalComposeResult(
                output_path=export.output_path if export else None,
                replaced=job.replaced if job else [],
                missing=job.missing if job else [],
                remaining_placeholders=remaining,
                section_count=len(proposal.get("sections") or []),
                table_count=len(proposal.get("tables") or []),
            ).model_dump()
            if export:
                updated_docs = merge_export_into_document_automation(updated_docs, export)
            if job:
                updated_docs = _merge_hwp_job_into_document_automation(updated_docs, job)

        drafts = dict(updated_docs.get("drafts") or {})
        drafts["proposal"] = proposal
        updated_docs["drafts"] = drafts
        if not validation_failure:
            updated_docs["errors"] = list(updated_docs.get("errors") or []) + errors
            _record_errors(conn, notice_no, errors)

            updated_analysis = dict(analysis)
            updated_analysis["document_automation"] = updated_docs
            next_status = advance_status(row["status"], "hwp_composed") if export else row["status"]
            conn.execute(
                update(bid_pipeline)
                .where(bid_pipeline.c.notice_no == notice_no)
                .values(analysis=updated_analysis, status=next_status)
            )
            response = ProposalComposeResponse(
                notice_no=notice_no,
                export=export,
                proposal=proposal,
                job=job,
                required_missing=required_missing,
                remaining_placeholders=remaining,
                errors=errors,
            )
    if validation_failure:
        raise HTTPException(
            status_code=409,
            detail={"message": "pre-compose validation failed", "errors": validation_failure},
        )
    assert response is not None
    return response
