from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select
from sqlalchemy.pool import StaticPool

from api.config import settings
from api.main import app
from api.routers import notices
from api.routers.notices import bid_pipeline, metadata
from api.services.document_automation import analyze_document_requirements


@pytest.fixture
def sqlite_engine(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    monkeypatch.setattr("api.db.get_engine", lambda: engine)
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    return engine


@pytest.fixture
def client(sqlite_engine, monkeypatch):
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    return TestClient(app)


def _seed(engine, *, status="analyzed", analysis=None):
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no="DOC-1",
                title="ABB 변압기 구매",
                source="G2B",
                raw={
                    "ntceInsttNm": "테스트기관",
                    "bidClseDt": "2026-06-10T10:00:00+09:00",
                    "cntrctCnclsMthdNm": "제한경쟁",
                    "presmptPrce": "30000000",
                },
                category="ABB장비",
                fit_score=82,
                assignee="이용문",
                analysis=analysis
                or {
                    "elec_spec": {
                        "product_category": "변압기",
                        "rated_voltage_kv": 22.9,
                        "rated_power_kva": 1000,
                    }
                },
                status=status,
                created_at=now,
                updated_at=now,
            )
        )


def test_rule_based_document_analysis_builds_checklist(sqlite_engine):
    _seed(sqlite_engine)
    with sqlite_engine.begin() as conn:
        row = conn.execute(select(bid_pipeline.c).where(bid_pipeline.c.notice_no == "DOC-1")).mappings().one()

    result = analyze_document_requirements(row)

    names = {item["name"] for item in result["checklist"]}
    assert "입찰참가신청서" in names
    assert "규격대응표" in names
    assert "사업자등록증" in names
    assert "technical_compliance" in result["drafts"]
    assert result["source"] == "rule"


def test_keyword_fallback_uses_attachment_text(sqlite_engine):
    """LLM 키 없을 때(폴백): 첨부 본문(text_excerpt)에 보증 키워드가 있으면 bid_bond가 필요로."""
    analysis = {
        "document_automation": {
            "uploads": [
                {"name": "공고서.hwp", "text_excerpt": "입찰보증금은 입찰금액의 5%를 납부"}
            ]
        }
    }
    _seed(sqlite_engine, analysis=analysis)
    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c).where(bid_pipeline.c.notice_no == "DOC-1")
        ).mappings().one()

    result = analyze_document_requirements(row)
    by_id = {i["id"]: i for i in result["checklist"]}
    assert by_id["bid_bond"]["required"] is True
    assert by_id["bid_bond"]["status"] == "needed"
    # 본문에 실적/면허 근거가 없으므로 해당없음 유지
    assert by_id["performance_record"]["status"] == "not_applicable"


def test_llm_judgment_uses_attachment_text_and_syncs_status(sqlite_engine, monkeypatch):
    """LLM 경로: 첨부 본문이 _llm_suggestions로 전달되고, required 판정이 status까지 동기화."""
    captured: dict = {}

    def fake_llm(row, attachments_text=""):
        captured["text"] = attachments_text
        return (
            {
                "checklist": [
                    {"id": "performance_record", "required": True, "reason": "본문에 납품실적 제한"},
                    {"id": "bid_bond", "required": False, "reason": "보증 요구 없음"},
                ]
            },
            None,
        )

    monkeypatch.setattr(
        "api.services.document_automation._llm_suggestions", fake_llm
    )
    analysis = {
        "document_automation": {
            "uploads": [{"name": "규격서.hwp", "text_excerpt": "납품실적 3년 ATTACHMARK"}]
        }
    }
    _seed(sqlite_engine, analysis=analysis)
    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c).where(bid_pipeline.c.notice_no == "DOC-1")
        ).mappings().one()

    result = analyze_document_requirements(row)
    assert "ATTACHMARK" in captured["text"]
    by_id = {i["id"]: i for i in result["checklist"]}
    assert by_id["performance_record"]["required"] is True
    assert by_id["performance_record"]["status"] == "needed"
    assert by_id["bid_bond"]["required"] is False
    assert by_id["bid_bond"]["status"] == "not_applicable"


def test_documents_analyze_endpoint_rejects_collected(client, sqlite_engine):
    _seed(sqlite_engine, status="collected")
    r = client.post("/notices/DOC-1/documents/analyze")
    assert r.status_code == 409


def test_documents_analyze_patch_and_validate(client, sqlite_engine):
    _seed(sqlite_engine)

    r = client.post("/notices/DOC-1/documents/analyze")
    assert r.status_code == 200, r.text
    body = r.json()["document_automation"]
    assert body["ready_for_submission"] is False
    assert body["missing_required"]

    item_id = body["checklist"][0]["id"]
    r = client.patch(
        f"/notices/DOC-1/documents/checklist/{item_id}",
        json={"status": "ready", "owner": "이용문", "note": "확인 완료"},
    )
    assert r.status_code == 200, r.text
    updated = r.json()["document_automation"]["checklist"][0]
    assert updated["status"] == "ready"
    assert updated["note"] == "확인 완료"
    assert "manual" in updated["source"]

    r = client.post("/notices/DOC-1/documents/validate")
    assert r.status_code == 200
    assert r.json()["ready_for_submission"] is False


def test_autofill_links_bid_form_draft(client, sqlite_engine, monkeypatch):
    _seed(sqlite_engine)
    client.post("/notices/DOC-1/documents/analyze")

    class FakeOutcome:
        template_path = "templates/bid.hwp"
        output_path = "output/DOC-1.hwp"
        placeholders = ["notice_no"]
        replaced = ["notice_no"]
        missing = []
        remaining_placeholders = []

    class FakeClient:
        def autofill_bid_form(self, **kwargs):
            return FakeOutcome()

    monkeypatch.setattr(notices, "_make_hwp_agent_client", lambda: FakeClient())

    r = client.post(
        "/notices/DOC-1/autofill-form",
        json={
            "template_path": "templates/bid.hwp",
            "output_path": "output/DOC-1.hwp",
            "values": {},
            "visible": False,
        },
    )
    assert r.status_code == 200, r.text

    with sqlite_engine.begin() as conn:
        row = conn.execute(select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "DOC-1")).mappings().one()
    docs = row["analysis"]["document_automation"]
    assert docs["drafts"]["bid_form"]["output_path"] == "output/DOC-1.hwp"
    bid_form = next(item for item in docs["checklist"] if item["id"] == "bid_form")
    assert bid_form["status"] == "generated"
