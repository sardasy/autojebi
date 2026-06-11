"""grade_notice_impl + GradeError 도메인 예외 테스트 (M5).

기존 test_grade_endpoint.py와 같은 in-memory SQLite 패턴.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool

from api.config import settings
from api.grading.schemas import FitSummary, QualificationInfo
from api.routers.notices import bid_pipeline, metadata
from api.services import grading_runner, qual_cache
from api.services.grading_runner import (
    GradeInvalidStatusError,
    GradeNotFoundError,
    grade_notice_impl,
)
from api.sku.schemas import AbbSku, SkuMatch


@pytest.fixture(autouse=True)
def _clear_qual_cache():
    """M6: 각 테스트 독립성 보장."""
    qual_cache.clear()
    yield
    qual_cache.clear()


@pytest.fixture
def sqlite_engine(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    monkeypatch.setattr(settings, "slack_webhook_url", "")
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    return engine


def _seed(engine, *, notice_no="T1-00", status="analyzed", elec=None, raw=None, base_price=None):
    now = datetime.now(tz=UTC)
    analysis = {"elec_spec": elec or {"product_category": "변압기", "rated_power_kva": 1000.0}}
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no=notice_no,
                title="강원본부 변압기 시험기",
                source="G2B",
                raw=raw or {"cntrctCnclsMthdNm": "제한경쟁"},
                category="ABB장비",
                fit_score=70,
                assignee="이용문",
                analysis=analysis,
                status=status,
                created_at=now,
                updated_at=now,
                bid_no="R26BK01543282",
                bid_seq="000",
                base_price=base_price,
            )
        )


def _patch_grading(monkeypatch, *, qual_info=None, fail_qual=False):
    """Qdrant + summarize + fetch_qual_safe 패치 (외부 의존성 차단)."""
    monkeypatch.setattr(
        grading_runner,
        "match_skus",
        lambda spec, limit=5, store=None: (
            "쿼리",
            [
                SkuMatch(
                    score=0.85,
                    sku=AbbSku(
                        sku_id="ABB-X",
                        name="RESIBLOC 1000kVA",
                        category="변압기",
                        description="d",
                    ),
                )
            ],
        ),
    )
    monkeypatch.setattr(
        grading_runner,
        "summarize_fit",
        lambda **_: FitSummary(reason="r", recommended_sku_id="ABB-X", risk_note=None),
    )
    if fail_qual:
        def _boom(bid_no, bid_seq):
            return None

        monkeypatch.setattr(grading_runner, "fetch_qual_safe", _boom)
    else:
        monkeypatch.setattr(
            grading_runner, "fetch_qual_safe", lambda bid_no, bid_seq: qual_info
        )


def test_not_found_raises_domain_error(sqlite_engine, monkeypatch):
    _patch_grading(monkeypatch, qual_info=None)
    with pytest.raises(GradeNotFoundError):
        grade_notice_impl(sqlite_engine, "MISSING", alert=False)


def test_invalid_status_raises_domain_error(sqlite_engine, monkeypatch):
    _seed(sqlite_engine, status="collected")
    _patch_grading(monkeypatch, qual_info=None)
    with pytest.raises(GradeInvalidStatusError) as exc_info:
        grade_notice_impl(sqlite_engine, "T1-00", alert=False)
    assert exc_info.value.current_status == "collected"


def test_grades_and_syncs_fit_score(sqlite_engine, monkeypatch):
    _seed(sqlite_engine, base_price=30_000_000)
    _patch_grading(monkeypatch, qual_info=None)

    result = grade_notice_impl(sqlite_engine, "T1-00", alert=False)
    assert result.score_spec == 0.85
    assert result.score_total > 0
    assert result.slack_delivered is False  # alert=False

    # DB 동기화
    from sqlalchemy import select

    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c).where(bid_pipeline.c.notice_no == "T1-00")
        ).mappings().one()
        assert row["fit_score"] == int(round(float(row["score_total"]) * 100))
        assert row["graded_at"] is not None


def test_qual_info_passed_to_score_qualification(sqlite_engine, monkeypatch):
    _seed(sqlite_engine)
    monkeypatch.setattr(settings, "abb_registered_regions", "서울,전국")
    qi = QualificationInfo(bid_no="R26BK01543282", bid_seq="000", regions=["부산"])
    _patch_grading(monkeypatch, qual_info=qi)

    result = grade_notice_impl(sqlite_engine, "T1-00", alert=False)
    # 전국 등록 → 부산도 통과 (region rule)
    assert result.score_qual == 1.0


def test_qual_info_none_falls_back_to_raw_json(sqlite_engine, monkeypatch):
    _seed(sqlite_engine, raw={"cntrctCnclsMthdNm": "수의계약"})
    _patch_grading(monkeypatch, qual_info=None)

    result = grade_notice_impl(sqlite_engine, "T1-00", alert=False)
    # qual_info 없음 + 수의계약 → raw_json 휴리스틱으로 0.5 감점
    assert result.score_qual == pytest.approx(0.5, abs=1e-6)


def test_qual_cache_hit_skips_second_fetch(sqlite_engine, monkeypatch):
    """M6: 같은 (bid_no, bid_seq)로 두 번 grade 시 fetch_qualifications가
    한 번만 호출되는지 검증 — 두 번째는 qual_cache hit으로 우회."""
    _seed(sqlite_engine, notice_no="T1-00")
    _seed(sqlite_engine, notice_no="T2-00")  # 동일 bid_no/bid_seq

    # 두 시드는 모두 bid_no="R26BK01543282", bid_seq="000"로 _seed 기본값 동일
    call_count = {"n": 0}

    async def fake_async(bid_no, bid_seq):
        call_count["n"] += 1
        return QualificationInfo(bid_no=bid_no, bid_seq=bid_seq, regions=["서울"])

    monkeypatch.setattr(grading_runner, "_fetch_qual_async", fake_async)
    monkeypatch.setattr(
        grading_runner,
        "match_skus",
        lambda spec, limit=5, store=None: (
            "q",
            [
                SkuMatch(
                    score=0.85,
                    sku=AbbSku(sku_id="X", name="n", category="변압기", description="d"),
                )
            ],
        ),
    )
    monkeypatch.setattr(
        grading_runner,
        "summarize_fit",
        lambda **_: FitSummary(reason="r", recommended_sku_id="X", risk_note=None),
    )

    # 두 번 호출
    grade_notice_impl(sqlite_engine, "T1-00", alert=False)
    grade_notice_impl(sqlite_engine, "T2-00", alert=False)

    # 같은 bid_no/bid_seq라 _fetch_qual_async는 1번만 호출
    assert call_count["n"] == 1
    assert qual_cache.size() == 1


def test_qual_cache_disabled_does_not_skip_fetch(sqlite_engine, monkeypatch):
    """QUAL_CACHE_ENABLED=false면 매번 fresh fetch."""
    monkeypatch.setattr(settings, "qual_cache_enabled", False)
    _seed(sqlite_engine, notice_no="T1-00")
    _seed(sqlite_engine, notice_no="T2-00")

    call_count = {"n": 0}

    async def fake_async(bid_no, bid_seq):
        call_count["n"] += 1
        return QualificationInfo(bid_no=bid_no, bid_seq=bid_seq, regions=["서울"])

    monkeypatch.setattr(grading_runner, "_fetch_qual_async", fake_async)
    monkeypatch.setattr(
        grading_runner,
        "match_skus",
        lambda spec, limit=5, store=None: (
            "q",
            [
                SkuMatch(
                    score=0.85,
                    sku=AbbSku(sku_id="X", name="n", category="변압기", description="d"),
                )
            ],
        ),
    )
    monkeypatch.setattr(
        grading_runner,
        "summarize_fit",
        lambda **_: FitSummary(reason="r", recommended_sku_id="X", risk_note=None),
    )

    grade_notice_impl(sqlite_engine, "T1-00", alert=False)
    grade_notice_impl(sqlite_engine, "T2-00", alert=False)

    # 캐시 비활성 → 매번 호출
    assert call_count["n"] == 2


def test_qdrant_failure_falls_back_to_empty_matches(sqlite_engine, monkeypatch):
    _seed(sqlite_engine)

    def boom(*_args, **_kwargs):
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(grading_runner, "_make_sku_matcher_store", boom)
    monkeypatch.setattr(
        grading_runner,
        "summarize_fit",
        lambda **_: FitSummary(reason="폴백", recommended_sku_id=None, risk_note=None),
    )
    monkeypatch.setattr(grading_runner, "fetch_qual_safe", lambda *_a: None)

    result = grade_notice_impl(sqlite_engine, "T1-00", alert=False)
    assert result.score_spec == 0.0  # top match 없음
    assert result.top_sku is None
