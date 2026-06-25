from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select
from sqlalchemy.pool import StaticPool

from api.config import settings
from api.main import app
from api.routers import notices
from api.routers.notices import bid_pipeline, metadata, notice_required_documents
from api.services.required_documents import find_candidate_segments


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


def _seed(engine, notice_no="REQ-1"):
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no=notice_no,
                title="시험장치 구매",
                source="G2B",
                raw={},
                category="혼합",
                fit_score=70,
                assignee="이용문",
                analysis={
                    "document_automation": {
                        "uploads": [
                            {
                                "name": "공고문.pdf",
                                "storage_path": "",
                                "mime": "application/pdf",
                                "text_excerpt": (
                                    "입찰자는 사업자등록증을 제출하여야 한다. "
                                    "가격제안서 및 산출내역서를 제출하여야 한다. "
                                    "대리인 참석 시 위임장을 제출한다."
                                ),
                            }
                        ]
                    }
                },
                status="documents_analyzed",
                created_at=now,
                updated_at=now,
            )
        )


_CANNED = [
    {
        "doc_name": "사업자등록증",
        "requirement_type": "required",
        "submit_stage": "bid",
        "source_file": "공고문.pdf",
        "page_no": 1,
        "deadline": "입찰서 제출 시",
        "condition": None,
        "evidence_text": "입찰자는 사업자등록증을 제출하여야 한다",
        "confidence": 0.92,
    },
    {
        "doc_name": "가격제안서",
        "requirement_type": "required",
        "submit_stage": "price",
        "source_file": "공고문.pdf",
        "page_no": 2,
        "deadline": "가격입찰 시",
        "condition": None,
        "evidence_text": "가격제안서 및 산출내역서를 제출하여야 한다",
        "confidence": 0.89,
    },
    {
        "doc_name": "위임장",
        "requirement_type": "conditional",
        "submit_stage": "conditional",
        "source_file": "공고문.pdf",
        "page_no": 1,
        "deadline": None,
        "condition": "대리인 참석 시",
        "evidence_text": "대리인 참석 시 위임장을 제출한다",
        "confidence": 0.85,
    },
]


def test_find_candidate_segments_picks_keyword_lines():
    pages = [
        {"source_file": "공고문.pdf", "page_no": 3, "text": (
            "일반 안내 문구입니다.\n입찰자는 사업자등록증을 제출하여야 한다.\n끝."
        )},
    ]
    segs = find_candidate_segments(pages)
    assert len(segs) == 1
    assert segs[0]["source_file"] == "공고문.pdf"
    assert segs[0]["page_no"] == 3
    assert "사업자등록증" in segs[0]["text"]


def test_analyze_upserts_and_lists(client, sqlite_engine, monkeypatch):
    _seed(sqlite_engine)
    monkeypatch.setattr(notices, "classify_required_documents", lambda candidates: _CANNED)

    r = client.post("/notices/REQ-1/required-documents/analyze")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["upserted"] == 3
    stages = {it["doc_name"]: it["submit_stage"] for it in body["items"]}
    assert stages["가격제안서"] == "price"
    assert stages["위임장"] == "conditional"
    # 정렬: bid 먼저
    assert body["items"][0]["submit_stage"] == "bid"

    g = client.get("/notices/REQ-1/required-documents")
    assert g.status_code == 200
    assert len(g.json()["items"]) == 3
    sample = next(i for i in g.json()["items"] if i["doc_name"] == "사업자등록증")
    assert sample["evidence_text"]
    assert sample["page_no"] == 1
    assert sample["requirement_type"] == "required"


def test_patch_check_persists_and_reanalyze_preserves(client, sqlite_engine, monkeypatch):
    _seed(sqlite_engine)
    monkeypatch.setattr(notices, "classify_required_documents", lambda candidates: _CANNED)
    client.post("/notices/REQ-1/required-documents/analyze")

    with sqlite_engine.begin() as conn:
        doc = conn.execute(
            select(notice_required_documents).where(
                notice_required_documents.c.notice_no == "REQ-1",
                notice_required_documents.c.doc_name == "사업자등록증",
            )
        ).mappings().one()

    p = client.patch(
        f"/notices/REQ-1/required-documents/{doc['id']}",
        json={"checked": True, "owner": "이용문"},
    )
    assert p.status_code == 200, p.text
    assert p.json()["checked"] is True
    assert p.json()["owner"] == "이용문"

    # 재분석해도 사람이 만진 checked/owner는 보존, 추출 필드는 갱신
    monkeypatch.setattr(
        notices,
        "classify_required_documents",
        lambda candidates: [{**_CANNED[0], "confidence": 0.99}],
    )
    client.post("/notices/REQ-1/required-documents/analyze")
    g = client.get("/notices/REQ-1/required-documents")
    again = next(i for i in g.json()["items"] if i["doc_name"] == "사업자등록증")
    assert again["checked"] is True
    assert again["owner"] == "이용문"
    assert abs(again["confidence"] - 0.99) < 1e-6


def test_analyze_404_for_unknown_notice(client, sqlite_engine):
    r = client.post("/notices/NOPE/required-documents/analyze")
    assert r.status_code == 404
