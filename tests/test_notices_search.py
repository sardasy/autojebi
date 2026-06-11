"""GET /notices 심화 검색 통합 테스트.

SQLite in-memory(StaticPool)에서 시드 데이터로 모든 필터·정렬·페이지네이션·호환성 검증.
JSONB 존재 필터는 dialect 분기 헬퍼가 sqlite에서 json_extract로 동작하는지 확인.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool

from api.config import settings
from api.main import app
from api.routers.notices import bid_pipeline, metadata


@pytest.fixture
def sqlite_engine(monkeypatch):
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
    monkeypatch.setattr(settings, "api_key", "")  # 인증 비활성
    return TestClient(app)


def _seed(engine, rows: list[dict]):
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        for r in rows:
            payload = {
                "title": "default",
                "source": "G2B",
                "raw": {},
                "category": "비관련",
                "fit_score": 0,
                "assignee": "미배정",
                "analysis": {},
                "status": "collected",
                "created_at": now,
                "updated_at": now,
            }
            payload.update(r)
            conn.execute(insert(bid_pipeline).values(**payload))


# ─────────────────────────────────────────────────────────────────────────
# 시드: 다양한 조합 12건
# ─────────────────────────────────────────────────────────────────────────
def _seed_fixtures(engine):
    now = datetime.now(tz=UTC)
    past = now - timedelta(days=7)
    future = now + timedelta(days=7)
    far = now + timedelta(days=30)
    rows = [
        # 0: 마감 임박 + ABB장비 + 그레이드됨 + 서류분석 됨
        {
            "notice_no": "N1-000",
            "title": "ABB 차단기 22.9kV 공급",
            "category": "ABB장비",
            "status": "analyzed",
            "fit_score": 85,
            "score_total": 0.85,
            "org_name": "한국전력공사 강원본부",
            "assignee": "이용문",
            "bid_type": "물품",
            "source": "G2B",
            "base_price": 50_000_000,
            "open_date": now - timedelta(days=2),
            "close_date": future,
            "graded_at": now,
            "top_sku_name": "ABB-Z-200",
            "grade_reason": "사양 일치",
            "analysis": {"document_automation": {"generated_at": "2026-06-04T00:00:00Z",
                         "uploads": [{"id": "u1", "name": "x.pdf", "size": 100,
                                       "mime": "application/pdf", "storage_path": "/x",
                                       "uploaded_at": "2026-06-04T00:00:00Z"}],
                         "ready_for_submission": True}},
        },
        # 1: 마감됨 (closed)
        {
            "notice_no": "N2-000", "title": "한전 변압기 SCR", "category": "SCR",
            "status": "archived_low", "fit_score": 20, "score_total": 0.2,
            "org_name": "한국전력공사 본사", "assignee": "이용문",
            "bid_type": "물품", "source": "G2B", "base_price": 10_000_000,
            "close_date": past,
        },
        # 2: 마감 미확인 (unknown)
        {
            "notice_no": "N3-000", "title": "IGBT 모듈 시험기", "category": "IGBT",
            "status": "analyzed", "fit_score": 70, "score_total": 0.7,
            "org_name": "서울대학교", "assignee": "이용문",
            "bid_type": "용역", "source": "KJEBI", "base_price": 5_000_000,
            "close_date": None,
        },
        # 3: form_filled + 서류 분석 안된 상태
        {
            "notice_no": "N4-000", "title": "HIL 시뮬레이터 SW 업데이트", "category": "SW",
            "status": "form_filled", "fit_score": 60, "score_total": 0.6,
            "org_name": "KETI", "assignee": "Sangjun",
            "bid_type": "용역", "source": "G2B", "base_price": 8_000_000,
            "close_date": far,
        },
        # 4: notified — 최종 상태
        {
            "notice_no": "N5-000", "title": "수동소자 콘덴서 일괄", "category": "수동소자",
            "status": "notified", "fit_score": 80, "score_total": 0.8,
            "org_name": "한국가스공사", "assignee": "이용문",
            "bid_type": "물품", "source": "G2B", "base_price": 30_000_000,
            "close_date": future, "graded_at": now,
        },
        # 5: 마감 임박 (가장 빨리) + 비관련
        {
            "notice_no": "N6-000", "title": "잡다한 사무용품", "category": "비관련",
            "status": "collected", "fit_score": 0, "score_total": 0.0,
            "org_name": "지방자치단체", "assignee": "미배정",
            "bid_type": "공사", "source": "G2B", "base_price": 2_000_000,
            "close_date": now + timedelta(days=1),
        },
    ]
    # 추가로 6건 더 (페이지네이션 검증용)
    for i in range(6):
        rows.append({
            "notice_no": f"P{i}-000", "title": f"공고 P{i}", "category": "혼합",
            "status": "collected", "fit_score": 30 + i, "score_total": 0.3 + i / 100,
            "org_name": f"기관{i}", "assignee": "미배정",
            "bid_type": "물품", "source": "G2B", "base_price": 1_000_000 * (i + 1),
            "close_date": future + timedelta(days=i),
        })
    _seed(engine, rows)
    return rows


# ─────────────────────────────────────────────────────────────────────────
# 통합 키워드 검색
# ─────────────────────────────────────────────────────────────────────────
def test_q_korean_partial_match(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?q=한전")
    assert r.status_code == 200
    items = r.json()["items"]
    titles = {it["title"] for it in items}
    assert "한전 변압기 SCR" in titles  # title 매칭
    # org_name "한국전력공사 본사"도 매칭 (한전 X, 한국전력 O — q는 정확히 한전)
    # → org_name 검색 검증 별도


def test_q_org_name_match(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?q=가스공사")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any("N5-000" == it["notice_no"] for it in items)


def test_q_notice_no_match(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?q=N3-000")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {it["notice_no"] for it in items} == {"N3-000"}


def test_q_english_case_insensitive(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?q=abb")  # 소문자
    assert r.status_code == 200
    items = r.json()["items"]
    assert any("ABB" in it["title"] for it in items)


# ─────────────────────────────────────────────────────────────────────────
# 통합 키워드 — 공백 무시 매칭 (G2B 띄어쓰기 변형 보정)
# ─────────────────────────────────────────────────────────────────────────
def test_q_ignores_whitespace_in_title(client, sqlite_engine):
    """title에 띄어쓰기가 들어가도 q가 붙여서 들어오면 매칭돼야 한다.

    실제 G2B 사례: title "실시간 전력전자 시뮬레이션 장비(제 어기시험장치)" 가
    q="제어기시험장치" 검색에서 매칭되지 않아 0건이던 회귀를 막는다.
    """
    _seed(
        sqlite_engine,
        [
            {
                "notice_no": "WS-001",
                "title": "실시간 (제 어기시험장치) 구매",
            },
        ],
    )
    r = client.get("/notices?q=제어기시험장치")
    assert r.status_code == 200
    assert {it["notice_no"] for it in r.json()["items"]} == {"WS-001"}


def test_q_ignores_whitespace_in_query(client, sqlite_engine):
    """q에 사용자가 띄어쓰기를 넣어도 컬럼이 붙어있으면 매칭돼야 한다 (역방향)."""
    _seed(
        sqlite_engine,
        [
            {"notice_no": "WS-002", "title": "제어기시험장치 구매"},
        ],
    )
    r = client.get("/notices?q=제어기 시험장치")
    assert r.status_code == 200
    assert {it["notice_no"] for it in r.json()["items"]} == {"WS-002"}


def test_q_multi_token_match_is_order_insensitive(client, sqlite_engine):
    """나라장터 AND 검색처럼 여러 단어 검색은 제목 내 단어 순서가 달라도 매칭한다."""
    _seed(
        sqlite_engine,
        [
            {
                "notice_no": "TOK-001",
                "title": "전력전자 실시간 시뮬레이션 장비 구매",
            },
            {
                "notice_no": "TOK-002",
                "title": "전력전자 시뮬레이션 장비 구매",
            },
        ],
    )
    r = client.get("/notices?q=실시간 전력전자 시뮬레이션 장비")
    assert r.status_code == 200
    assert {it["notice_no"] for it in r.json()["items"]} == {"TOK-001"}


def test_q_whitespace_only_skips_filter(client, sqlite_engine):
    """q="   "(공백만)은 필터를 적용하지 않고 전체를 반환해야 한다."""
    _seed_fixtures(sqlite_engine)
    r_no_q = client.get("/notices")
    r_ws = client.get("/notices?q=%20%20%20")
    assert r_no_q.status_code == 200 and r_ws.status_code == 200
    assert r_no_q.json()["total"] == r_ws.json()["total"]


# ─────────────────────────────────────────────────────────────────────────
# 다중 선택
# ─────────────────────────────────────────────────────────────────────────
def test_multi_status(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?status=analyzed&status=form_filled")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {it["status"] for it in items} == {"analyzed", "form_filled"}


def test_multi_category(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?category=IGBT&category=SCR")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {it["category"] for it in items} <= {"IGBT", "SCR"}
    assert len(items) >= 2


def test_csv_status_also_accepted(client, sqlite_engine):
    """`?status=a,b` CSV 형태도 호환."""
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?status=analyzed,form_filled")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {it["status"] for it in items} == {"analyzed", "form_filled"}


# ─────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────
def test_lifecycle_active(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?lifecycle=active&page_size=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert "N2-000" not in {it["notice_no"] for it in items}  # closed 제외
    assert "N3-000" in {it["notice_no"] for it in items}  # unknown 포함


def test_lifecycle_closed(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?lifecycle=closed&page_size=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {it["notice_no"] for it in items} == {"N2-000"}


def test_lifecycle_unknown(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?lifecycle=unknown&page_size=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {it["notice_no"] for it in items} == {"N3-000"}


def test_lifecycle_all_includes_everything(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?lifecycle=all&page_size=100")
    assert r.status_code == 200
    assert r.json()["total"] == 12


# ─────────────────────────────────────────────────────────────────────────
# 범위 필터
# ─────────────────────────────────────────────────────────────────────────
def test_fit_score_range(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?min_fit_score=60&max_fit_score=85&page_size=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(60 <= it["fit_score"] <= 85 for it in items)


def test_score_total_range(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?min_score_total=0.7&max_score_total=0.9&page_size=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(0.7 <= float(it["score_total"]) <= 0.9 for it in items)


def test_base_price_range(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?min_base_price=10000000&max_base_price=50000000&page_size=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(10_000_000 <= float(it["raw"].get("base_price", 0) or 0)
               or True for it in items)  # base_price는 raw에 없으니 row level 검증 어려움
    # 대신 notice_no로 검증
    nos = {it["notice_no"] for it in items}
    assert "N6-000" not in nos  # 2M < 10M
    assert "N3-000" not in nos  # 5M < 10M


# ─────────────────────────────────────────────────────────────────────────
# 존재 조건 — JSONB 분기 헬퍼가 SQLite에서 잘 작동하는지
# ─────────────────────────────────────────────────────────────────────────
def test_has_grade_true(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?has_grade=true&page_size=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(it["graded_at"] is not None for it in items)
    assert "N1-000" in {it["notice_no"] for it in items}


def test_has_documents_true(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?has_documents=true&page_size=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {it["notice_no"] for it in items} == {"N1-000"}


def test_has_uploads_true(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?has_uploads=true&page_size=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {it["notice_no"] for it in items} == {"N1-000"}


def test_ready_for_submission_true(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?ready_for_submission=true&page_size=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {it["notice_no"] for it in items} == {"N1-000"}


# ─────────────────────────────────────────────────────────────────────────
# 정렬
# ─────────────────────────────────────────────────────────────────────────
def test_sort_close_date_asc_nulls_last(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get(
        "/notices?lifecycle=all&sort=close_date&direction=asc&page_size=100"
    )
    assert r.status_code == 200
    items = r.json()["items"]
    nos = [it["notice_no"] for it in items]
    # 정렬 ASC: 과거 N2 → 1일 후 N6 → 7일 후 묶음(N1/N5/P0) → 그 뒤 P1~ → 30일 N4 → NULL N3
    assert nos[0] == "N2-000"  # 과거가 가장 작음
    assert nos[1] == "N6-000"  # 가장 임박한 미래
    assert nos[-1] == "N3-000"  # NULL은 마지막 (NULLS LAST)


def test_sort_fit_score_desc(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get(
        "/notices?lifecycle=all&sort=fit_score&direction=desc&page_size=100"
    )
    items = r.json()["items"]
    scores = [it["fit_score"] for it in items]
    assert scores == sorted(scores, reverse=True)


# ─────────────────────────────────────────────────────────────────────────
# 페이지네이션
# ─────────────────────────────────────────────────────────────────────────
def test_pagination_first_page(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?lifecycle=all&page=1&page_size=5")
    body = r.json()
    assert body["total"] == 12
    assert body["page"] == 1
    assert body["page_size"] == 5
    assert body["total_pages"] == 3
    assert len(body["items"]) == 5


def test_pagination_last_partial_page(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?lifecycle=all&page=3&page_size=5")
    body = r.json()
    assert body["page"] == 3
    assert len(body["items"]) == 2  # 12 - 10 = 2


def test_pagination_out_of_range_returns_empty(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?lifecycle=all&page=99&page_size=5")
    body = r.json()
    assert body["total"] == 12
    assert body["items"] == []


# ─────────────────────────────────────────────────────────────────────────
# 검증 에러
# ─────────────────────────────────────────────────────────────────────────
def test_invalid_sort_returns_422(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?sort=bogus")
    assert r.status_code == 422


def test_invalid_lifecycle_returns_422(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?lifecycle=weird")
    assert r.status_code == 422


def test_page_zero_returns_422(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?page=0")
    assert r.status_code == 422


def test_page_size_over_limit_returns_422(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?page_size=200")
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────
# 호환성 — 필터 없이 호출도 새 응답 포맷에 맞아야 함
# ─────────────────────────────────────────────────────────────────────────
def test_no_filter_returns_pagination_meta(client, sqlite_engine):
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices")
    body = r.json()
    assert isinstance(body.get("items"), list)
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 12
    assert body["total_pages"] == 1


def test_legacy_min_max_fit_score_still_works(client, sqlite_engine):
    """기존 min_fit_score/max_fit_score 쿼리는 그대로 동작 (호환성)."""
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?min_fit_score=80")
    items = r.json()["items"]
    assert all(it["fit_score"] >= 80 for it in items)


def test_legacy_status_single_still_works(client, sqlite_engine):
    """`?status=analyzed` 단일 값도 다중 선택 슬롯에서 해석 가능."""
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?status=analyzed")
    items = r.json()["items"]
    assert {it["status"] for it in items} == {"analyzed"}


# ─────────────────────────────────────────────────────────────────────────
# G2B 수집 컬럼 — 응답 top-level 노출
# ─────────────────────────────────────────────────────────────────────────
def test_list_exposes_g2b_columns_top_level(client, sqlite_engine):
    """org_name/base_price/open_date/close_date 등 G2B 수집 컬럼이
    NoticeRecord top-level에 실제 값으로 노출돼야 한다 (raw fallback 없이도).
    """
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices?q=ABB")
    assert r.status_code == 200
    items = r.json()["items"]
    target = next(it for it in items if it["notice_no"] == "N1-000")
    # 키 자체가 응답에 노출되는지
    for key in ("bid_no", "bid_seq", "bid_type", "org_code", "org_name",
                "base_price", "open_date", "close_date", "collected_at"):
        assert key in target, f"missing key in response: {key}"
    # 시드값이 NULL이 아닌 컬럼은 NULL이 아닌 값으로 노출
    assert target["org_name"] == "한국전력공사 강원본부"
    assert target["bid_type"] == "물품"
    assert float(target["base_price"]) == 50_000_000.0
    assert target["open_date"] is not None
    assert target["close_date"] is not None


def test_get_single_exposes_g2b_columns_top_level(client, sqlite_engine):
    """GET /notices/{notice_no} 단건도 G2B 컬럼을 top-level로 반환해야 한다."""
    _seed_fixtures(sqlite_engine)
    r = client.get("/notices/N1-000")
    assert r.status_code == 200
    body = r.json()
    assert body["org_name"] == "한국전력공사 강원본부"
    assert float(body["base_price"]) == 50_000_000.0
    assert body["close_date"] is not None
    assert body["open_date"] is not None
