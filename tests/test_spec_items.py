from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import insert, select, update

from api.routers.notices import (
    bid_pipeline,
    company_profiles,
    document_field_mappings,
    hwp_templates,
    notice_spec_items,
)
from api.services.hwp_agent_client import HwpAgentError, PutFieldsOutcome


def _seed_notice(engine, *, with_docs: bool = True) -> None:
    analysis = {
        "elec_spec": {
            "product_category": "변압기",
            "quantity": 2,
            "rated_voltage_kv": 22.9,
            "rated_power_kva": 1000.0,
            "standards": ["KS C", "IEC 60076"],
        }
    }
    if with_docs:
        analysis["document_automation"] = {
            "checklist": [
                {
                    "id": "bid_form",
                    "name": "입찰참가신청서",
                    "type": "bid_form",
                    "required": True,
                    "status": "needed",
                    "source": "rule",
                },
                {
                    "id": "technical_compliance",
                    "name": "규격대응표",
                    "type": "technical",
                    "required": True,
                    "status": "needed",
                    "source": "rule",
                },
            ],
            "drafts": {
                "technical_compliance": {
                    "kind": "markdown",
                    "label": "규격대응표 초안",
                    "content": "| 항목 | 공고 요구사양 |\n| --- | --- |",
                },
                "bid_form_values": {
                    "kind": "json",
                    "label": "HWP autofill 보강 입력값",
                    "values": {"notice_no": "SPEC-1"},
                },
            },
            "risks": [],
            "generated_at": "2026-06-21T00:00:00Z",
            "source": "rule",
            "ready_for_submission": False,
            "missing_required": [],
            "errors": [],
            "uploads": [],
            "exports": [],
        }
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no="SPEC-1",
                title="22.9kV 변압기 구매",
                source="E2E",
                raw={"ntceInsttNm": "한국전력공사", "ntceSpecFileNm1": "규격서.hwp"},
                category="ABB장비",
                fit_score=80,
                assignee="미배정",
                analysis=analysis,
                status="analyzed",
            )
        )


def _seed_hwp_mapping(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(company_profiles).values(
                profile_key="default",
                company_name="테스트회사",
                business_number="1234567890",
                ceo_name="대표",
                address="서울",
                profile_metadata={},
                active=True,
            )
        )
        bid_template_id = conn.execute(
            insert(hwp_templates).values(
                template_key="bid_form",
                kind="bid_form",
                name="입찰참가신청서",
                template_path="templates/입찰참가신청서_양식.hwp",
                template_version="put_fields_v1",
                active=True,
            )
        ).inserted_primary_key[0]
        proposal_template_id = conn.execute(
            insert(hwp_templates).values(
                template_key="proposal",
                kind="proposal",
                name="제안서",
                template_path="templates/제안서_양식.hwp",
                template_version="put_fields_v1",
                active=True,
            )
        ).inserted_primary_key[0]
        for template_id, rows in (
            (
                bid_template_id,
                [
                    ("notice_no", "notice.notice_no", True, "strip"),
                    ("technical_compliance_summary", "proposal.technical_compliance_summary", False, "truncate_1000"),
                ],
            ),
            (
                proposal_template_id,
                [
                    ("notice_no", "notice.notice_no", True, "strip"),
                    ("company_name", "company.company_name", True, "strip"),
                    ("technical_compliance_summary", "proposal.values.technical_compliance_summary", True, "truncate_1000"),
                ],
            ),
        ):
            for sort_order, (field, path, required, transform) in enumerate(rows, start=10):
                conn.execute(
                    insert(document_field_mappings).values(
                        template_id=template_id,
                        hwp_field_name=field,
                        context_path=path,
                        required=required,
                        transform=transform,
                        sort_order=sort_order,
                        active=True,
                    )
                )


def test_extract_spec_items_upserts_from_elec_spec(client, sqlite_engine):
    _seed_notice(sqlite_engine)

    r = client.post("/notices/SPEC-1/spec-items/extract")
    assert r.status_code == 200
    body = r.json()
    assert body["upserted"] >= 10
    product = next(item for item in body["items"] if item["item_key"] == "product_category")
    assert product["required_value"] == "변압기"
    assert product["status"] == "candidate"
    assert product["source_text"]
    assert product["review_priority"] == "normal"
    low_confidence = next(item for item in body["items"] if item["item_key"] == "rated_current_a")
    assert low_confidence["confidence"] < 0.75
    assert low_confidence["review_priority"] == "high"

    r2 = client.post("/notices/SPEC-1/spec-items/extract")
    assert r2.status_code == 200
    with sqlite_engine.begin() as conn:
        count = conn.execute(select(notice_spec_items.c.id)).all()
    assert len(count) == len(body["items"])


def test_extract_preserves_reviewed_manual_values(client, sqlite_engine):
    _seed_notice(sqlite_engine)
    client.post("/notices/SPEC-1/spec-items/extract")
    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(notice_spec_items.c.id).where(notice_spec_items.c.item_key == "rated_voltage_kv")
        ).one()
        conn.execute(
            update(notice_spec_items)
            .where(notice_spec_items.c.id == row.id)
            .values(
                proposed_value="22.9kV 대응",
                status="reviewed",
                note="담당자 확인",
                reviewed_by="manual-user",
                reviewed_at=datetime(2026, 6, 21, tzinfo=UTC),
                locked_fields=["required_value"],
                required_value="수동 요구값",
            )
        )

    client.post("/notices/SPEC-1/spec-items/extract")
    r = client.get("/notices/SPEC-1/spec-items")
    item = next(item for item in r.json()["items"] if item["item_key"] == "rated_voltage_kv")
    assert item["proposed_value"] == "22.9kV 대응"
    assert item["status"] == "reviewed"
    assert item["note"] == "담당자 확인"
    assert item["reviewed_by"] == "manual-user"
    assert item["locked_fields"] == ["required_value"]
    assert item["required_value"] == "수동 요구값"


def test_patch_spec_item_updates_document_draft(client, sqlite_engine):
    _seed_notice(sqlite_engine)
    r = client.post("/notices/SPEC-1/spec-items/extract")
    item_id = next(item["id"] for item in r.json()["items"] if item["item_key"] == "quantity")

    r2 = client.patch(
        f"/notices/SPEC-1/spec-items/{item_id}",
        json={"proposed_value": "2대 납품", "status": "matched"},
    )
    assert r2.status_code == 200
    with sqlite_engine.begin() as conn:
        analysis = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "SPEC-1")
        ).scalar_one()
    content = analysis["document_automation"]["drafts"]["technical_compliance"]["content"]
    assert "2대 납품" in content


def test_hwp_compose_requires_spec_items(client, sqlite_engine):
    _seed_notice(sqlite_engine)
    r = client.post("/notices/SPEC-1/documents/hwp-compose", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["errors"][0]["detail"] == "규격 항목 추출 필요"


def test_hwp_compose_uses_spec_items_and_persists_exports(client, sqlite_engine, monkeypatch):
    _seed_notice(sqlite_engine)
    _seed_hwp_mapping(sqlite_engine)
    client.post("/notices/SPEC-1/spec-items/extract")

    class FakeClient:
        def put_fields(self, **kwargs):
            assert "technical_compliance_summary" in kwargs["values"]
            return PutFieldsOutcome(
                output_path=kwargs["output_path"],
                replaced=["notice_no"],
                missing=[],
                remaining_placeholders=[],
                raw={},
            )

        def generate_compliance_table(self, **kwargs):
            assert kwargs["headers"] == ["항목", "공고 요구사양", "제안/대응 사양", "단위", "확인상태", "근거"]
            return {"output_path": kwargs["output_path"], "sheet_count": 1}

    monkeypatch.setattr("api.routers.notices._common._make_hwp_agent_client", lambda: FakeClient())
    r = client.post("/notices/SPEC-1/documents/hwp-compose", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "form_filled"
    assert body["technical_compliance"]["kind"] == "hwp"
    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c.status, bid_pipeline.c.analysis).where(
                bid_pipeline.c.notice_no == "SPEC-1"
            )
        ).one()
    assert row.status == "form_filled"
    assert any(item["kind"] == "hwp" for item in row.analysis["document_automation"]["exports"])


def test_proposal_compose_requires_spec_items(client, sqlite_engine):
    _seed_notice(sqlite_engine)

    r = client.post("/notices/SPEC-1/documents/proposal-compose", json={})

    assert r.status_code == 409
    assert r.json()["detail"]["errors"][0]["detail"] == "규격 항목 추출 필요"


def test_proposal_compose_persists_draft_and_export(client, sqlite_engine, monkeypatch, tmp_path):
    _seed_notice(sqlite_engine)
    _seed_hwp_mapping(sqlite_engine)
    client.post("/notices/SPEC-1/spec-items/extract")
    final_path = tmp_path / "proposal.hwp"
    final_path.write_bytes(b"HWP")

    class FakeClient:
        def put_fields(self, **kwargs):
            assert kwargs["values"]["notice_no"] == "SPEC-1"
            assert "technical_compliance_summary" in kwargs["values"]
            return PutFieldsOutcome(
                output_path=str(final_path),
                replaced=["notice_no"],
                missing=[],
                remaining_placeholders=[],
                raw={},
            )

    monkeypatch.setattr("api.routers.notices._common._make_hwp_agent_client", lambda: FakeClient())
    r = client.post(
        "/notices/SPEC-1/documents/proposal-compose",
        json={"values_override": {"company_name": "테스트회사"}},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["export"]["kind"] == "proposal_hwp"
    assert body["proposal"]["values"]["company_name"] == "테스트회사"
    with sqlite_engine.begin() as conn:
        analysis = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "SPEC-1")
        ).scalar_one()
    docs = analysis["document_automation"]
    assert "proposal" in docs["drafts"]
    assert docs["exports"][0]["kind"] == "proposal_hwp"


def test_proposal_compose_remaining_placeholders_marks_export_warning(
    client,
    sqlite_engine,
    monkeypatch,
    tmp_path,
):
    _seed_notice(sqlite_engine)
    _seed_hwp_mapping(sqlite_engine)
    client.post("/notices/SPEC-1/spec-items/extract")
    final_path = tmp_path / "proposal-warning.hwp"
    final_path.write_bytes(b"HWP")

    class FakeClient:
        def put_fields(self, **kwargs):
            return PutFieldsOutcome(
                output_path=str(final_path),
                replaced=["notice_no"],
                missing=[],
                remaining_placeholders=["company_name"],
                raw={},
            )

    monkeypatch.setattr("api.routers.notices._common._make_hwp_agent_client", lambda: FakeClient())
    r = client.post("/notices/SPEC-1/documents/proposal-compose", json={})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["remaining_placeholders"] == ["company_name"]
    assert body["export"]["validation_status"] == "warning"
    assert body["export"]["validation_errors"]
    assert body["errors"][-1]["stage"] == "hwp.remaining_placeholders"


def test_proposal_compose_agent_failure_keeps_draft_without_export(
    client,
    sqlite_engine,
    monkeypatch,
):
    _seed_notice(sqlite_engine)
    _seed_hwp_mapping(sqlite_engine)
    client.post("/notices/SPEC-1/spec-items/extract")

    class FakeClient:
        def put_fields(self, **kwargs):
            raise HwpAgentError("agent missing /document/put-fields")

    monkeypatch.setattr("api.routers.notices._common._make_hwp_agent_client", lambda: FakeClient())
    r = client.post("/notices/SPEC-1/documents/proposal-compose", json={})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["export"] is None
    assert any(item["stage"] == "hwp.put_fields" for item in body["errors"])
    with sqlite_engine.begin() as conn:
        analysis = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "SPEC-1")
        ).scalar_one()
    docs = analysis["document_automation"]
    assert "proposal" in docs["drafts"]
    assert docs["exports"] == []
