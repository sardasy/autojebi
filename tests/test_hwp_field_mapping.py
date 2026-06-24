from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, select

from api.routers.notices import (
    bid_pipeline,
    company_profiles,
    document_field_mappings,
    hwp_generation_jobs,
    hwp_templates,
)
from api.services.hwp_agent_client import PutFieldsOutcome
from api.services.hwp_fields import resolve_hwp_fields


def test_resolve_hwp_fields_applies_overrides_defaults_and_transforms():
    context = {
        "company": {"business_number": "1234567890"},
        "notice": {"notice_no": "N-1", "base_price": "1234567", "close_date": "20260624"},
    }
    resolved = resolve_hwp_fields(
        context=context,
        mappings=[
            {
                "hwp_field_name": "notice_no",
                "context_path": "notice.notice_no",
                "required": True,
                "transform": "strip",
            },
            {
                "hwp_field_name": "business_number",
                "context_path": "company.business_number",
                "transform": "business_number_dash",
            },
            {
                "hwp_field_name": "base_price",
                "context_path": "notice.base_price",
                "transform": "number_comma",
            },
            {
                "hwp_field_name": "close_date",
                "context_path": "notice.close_date",
                "transform": "date_yyyy_mm_dd",
            },
            {
                "hwp_field_name": "fallback",
                "context_path": "missing.value",
                "default_value": "기본값",
                "transform": "none",
            },
        ],
        values_override={"notice_no": " OVERRIDE "},
    )

    assert resolved.input_values["notice_no"] == "OVERRIDE"
    assert resolved.input_values["business_number"] == "123-45-67890"
    assert resolved.input_values["base_price"] == "1,234,567"
    assert resolved.input_values["close_date"] == "2026-06-24"
    assert resolved.input_values["fallback"] == "기본값"
    assert resolved.required_missing == []


def test_resolve_hwp_fields_rejects_unknown_transform():
    with pytest.raises(ValueError, match="unsupported transform"):
        resolve_hwp_fields(
            context={},
            mappings=[
                {
                    "hwp_field_name": "x",
                    "context_path": "x",
                    "transform": "eval",
                }
            ],
        )


def _seed_notice_and_mapping(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no="HWP-1",
                title="HWP 테스트",
                source="test",
                raw={"ntceInsttNm": "발주처"},
                category="ABB장비",
                fit_score=90,
                analysis={
                    "document_automation": {
                        "checklist": [],
                        "drafts": {},
                        "risks": [],
                        "generated_at": datetime.now(tz=UTC).isoformat(),
                        "source": "test",
                        "ready_for_submission": False,
                        "missing_required": [],
                        "errors": [],
                        "uploads": [],
                        "exports": [],
                    }
                },
                status="analyzed",
            )
        )
        conn.execute(
            insert(company_profiles).values(
                profile_key="default",
                company_name="미림씨스콘",
                profile_metadata={},
                active=True,
            )
        )
        template_id = conn.execute(
            insert(hwp_templates).values(
                template_key="bid_form",
                kind="bid_form",
                name="입찰참가신청서",
                template_path="templates/form.hwp",
                template_version="put_fields_v1",
                active=True,
            )
        ).inserted_primary_key[0]
        conn.execute(
            insert(document_field_mappings).values(
                template_id=template_id,
                hwp_field_name="notice_no",
                context_path="notice.notice_no",
                required=True,
                transform="strip",
                active=True,
            )
        )


def test_hwp_context_templates_and_review_api(client, sqlite_engine, monkeypatch, tmp_path):
    _seed_notice_and_mapping(sqlite_engine)
    out = tmp_path / "filled.hwp"
    out.write_bytes(b"HWP")

    class FakeClient:
        def put_fields(self, **kwargs):
            return PutFieldsOutcome(
                output_path=str(out),
                replaced=["notice_no"],
                missing=[],
                remaining_placeholders=["address"],
                raw={"queued": True},
            )

    monkeypatch.setattr("api.routers.notices._make_hwp_agent_client", lambda: FakeClient())

    templates = client.get("/documents/hwp-templates")
    assert templates.status_code == 200
    assert templates.json()["items"][0]["mappings"][0]["hwp_field_name"] == "notice_no"

    preview = client.post("/notices/HWP-1/documents/hwp-context", json={"template_key": "bid_form"})
    assert preview.status_code == 200
    assert preview.json()["input_values"]["notice_no"] == "HWP-1"

    generated = client.post("/notices/HWP-1/documents/hwp-put-fields", json={"template_key": "bid_form"})
    assert generated.status_code == 200
    body = generated.json()
    assert body["export"]["kind"] == "bid_form_hwp"
    assert body["remaining_placeholders"] == ["address"]
    job_id = body["job"]["id"]

    reviewed = client.post(
        f"/notices/HWP-1/documents/hwp-jobs/{job_id}/review",
        json={"review_status": "approved", "reviewed_by": "tester"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["job"]["review_status"] == "approved"
    with sqlite_engine.begin() as conn:
        job = conn.execute(
            select(hwp_generation_jobs).where(hwp_generation_jobs.c.id == job_id)
        ).mappings().one()
    assert job["review_status"] == "approved"
