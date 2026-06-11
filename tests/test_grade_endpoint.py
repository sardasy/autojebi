"""POST /notices/{notice_no}/grade 통합 단위 테스트.

DB는 in-memory SQLite (postgres dialect의 ON CONFLICT/Numeric 등은 안 쓰는 부분이라 호환).
extractor·Qdrant·Slack은 monkeypatch로 격리.

핵심 검증:
  - analyzed 공고에 grade 호출 시 score_* 컬럼이 채워지고 fit_score = int(total*100)
  - status는 변동 없음
  - Qdrant 실패 시 빈 matches로 폴백 (raise 안함)
  - body.alert=False 또는 임계치 미달 시 Slack 발송 안함
  - 잘못된 status에서 호출 시 409
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool

from api.config import settings
from api.grading.schemas import FitSummary
from api.llm.schemas import ElecSpec
from api.main import app
from api.routers.notices import bid_pipeline, metadata
from api.sku.schemas import AbbSku, SkuMatch


@pytest.fixture
def sqlite_engine(monkeypatch):
    # StaticPool로 단일 연결 공유 — :memory: SQLite가 connection-isolated인 문제 회피
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    monkeypatch.setattr("api.db.get_engine", lambda: engine)
    return engine


@pytest.fixture
def client(sqlite_engine, monkeypatch):
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    monkeypatch.setattr(settings, "slack_webhook_url", "")  # 기본 Slack 비활성
    monkeypatch.setattr(settings, "api_key", "")  # M9 인증 비활성 (auth_enabled→False)
    # M5: 모든 grade 테스트에서 fetch_qual_safe 차단 (G2B 라이브 호출 안함)
    monkeypatch.setattr(
        "api.services.grading_runner.fetch_qual_safe",
        lambda bid_no, bid_seq: None,
    )
    return TestClient(app)


def _seed_notice(engine, *, notice_no="T1-00", status="analyzed", elec=None, base_price=None):
    now = datetime.now(tz=UTC)
    analysis = {"elec_spec": elec or {"product_category": "변압기", "rated_power_kva": 1000.0}}
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no=notice_no,
                title="강원본부 변압기 시험기",
                source="G2B",
                raw={"cntrctCnclsMthdNm": "제한경쟁", "presmptPrce": "30000000"},
                category="ABB장비",
                fit_score=70,
                assignee="이용문",
                analysis=analysis,
                status=status,
                created_at=now,
                updated_at=now,
                base_price=base_price,
            )
        )


def _fake_summary(reason="변압기 22.9kV 1000kVA 공고로 ABB와 적합합니다."):
    def _impl(**kwargs):
        return FitSummary(reason=reason, recommended_sku_id="ABB-X", risk_note=None)

    return _impl


def _fake_match_returning(score: float = 0.85):
    def _impl(spec: ElecSpec, limit: int = 5, store=None):
        match = SkuMatch(
            score=score,
            sku=AbbSku(sku_id="ABB-X", name="RESIBLOC 1000kVA", category="변압기", description="d"),
        )
        return "query 변압기", [match]

    return _impl


def test_grade_fills_score_columns_and_syncs_fit_score(client, sqlite_engine, monkeypatch):
    _seed_notice(sqlite_engine, base_price=30_000_000)
    monkeypatch.setattr("api.services.grading_runner.match_skus", _fake_match_returning(0.9))
    monkeypatch.setattr("api.services.grading_runner.summarize_fit", _fake_summary())

    r = client.post("/notices/T1-00/grade", json={"alert": False})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["score_spec"] == 0.9
    assert body["score_qual"] >= 0.5  # raw에 cntrctCnclsMthdNm=제한경쟁 → no penalty → 1.0
    assert body["score_total"] > 0.0
    assert body["top_sku"] == "ABB-X"
    assert body["status"] == "analyzed"  # status 변동 없음
    assert body["slack_delivered"] is False  # alert=False

    # DB 확인
    with sqlite_engine.begin() as conn:
        from sqlalchemy import select

        row = conn.execute(select(bid_pipeline.c).where(bid_pipeline.c.notice_no == "T1-00")).mappings().one()
        assert row["status"] == "analyzed"
        assert row["score_total"] is not None
        assert row["fit_score"] == int(round(float(row["score_total"]) * 100))
        assert row["graded_at"] is not None
        assert "grade" in (row["analysis"] or {})


def test_grade_returns_404_when_notice_missing(client, sqlite_engine):
    r = client.post("/notices/NOEXIST/grade", json={"alert": False})
    assert r.status_code == 404


def test_grade_returns_409_when_status_invalid(client, sqlite_engine, monkeypatch):
    _seed_notice(sqlite_engine, status="collected")
    monkeypatch.setattr("api.services.grading_runner.match_skus", _fake_match_returning())
    monkeypatch.setattr("api.services.grading_runner.summarize_fit", _fake_summary())

    r = client.post("/notices/T1-00/grade", json={"alert": False})
    assert r.status_code == 409


def test_grade_falls_back_when_qdrant_raises(client, sqlite_engine, monkeypatch):
    _seed_notice(sqlite_engine)

    def boom(*args, **kwargs):
        raise RuntimeError("qdrant down")

    monkeypatch.setattr("api.services.grading_runner._make_sku_matcher_store", boom)
    # 매칭 없을 때의 realistic fallback: recommended_sku_id=None
    def empty_summary(**kwargs):
        return FitSummary(reason="폴백 사유 (매칭 없음)", recommended_sku_id=None, risk_note=None)

    monkeypatch.setattr("api.services.grading_runner.summarize_fit", empty_summary)

    r = client.post("/notices/T1-00/grade", json={"alert": False})
    assert r.status_code == 200
    body = r.json()
    assert body["score_spec"] == 0.0  # top match 없음
    assert body["top_sku"] in (None, "")
    # analysis.errors에 stage=grade.qdrant 기록
    with sqlite_engine.begin() as conn:
        from sqlalchemy import select

        row = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "T1-00")
        ).mappings().one()
        errors = (row["analysis"] or {}).get("errors") or []
        assert any(e.get("stage") == "grade.qdrant" for e in errors)


def test_grade_skips_slack_below_threshold(client, sqlite_engine, monkeypatch):
    _seed_notice(sqlite_engine)
    monkeypatch.setattr(settings, "slack_webhook_url", "https://hooks.slack.test/X")
    monkeypatch.setattr(settings, "grade_alert_threshold", 0.99)  # 임계 매우 높음
    monkeypatch.setattr("api.services.grading_runner.match_skus", _fake_match_returning(0.5))
    monkeypatch.setattr("api.services.grading_runner.summarize_fit", _fake_summary())

    # SlackNotifier가 호출되면 안됨 — 보호용 monkeypatch (M5: grading_runner로 이동)
    called = {"n": 0}
    from api.services.grading_runner import SlackNotifier as RealSlack

    class Counting(RealSlack):
        def send_grade_alert(self, **kwargs):
            called["n"] += 1
            return super().send_grade_alert(**kwargs)

    monkeypatch.setattr("api.services.grading_runner.SlackNotifier", Counting)

    r = client.post("/notices/T1-00/grade", json={"alert": True})
    assert r.status_code == 200
    assert r.json()["slack_delivered"] is False
    assert called["n"] == 0  # 임계치 미달이면 호출 자체 안함
