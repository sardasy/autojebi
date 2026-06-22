"""M13 — POST /notices/search 통합 테스트.

검증 범위:
  - 422 (빈 키워드 / start > end / 90일 초과)
  - 502 (G2B HTTP/파싱 실패)
  - already_exists 표시 (source='G2B' + notice_no 매칭)
  - dedup (G2B에서 같은 (bid_no, bid_seq) 중복 응답)
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import insert

from api.collector import pipeline
from api.collector.g2b_client import RawBid
from api.routers.notices import bid_pipeline

# sqlite_engine, client fixture는 tests/conftest.py에서 제공


def _seed_existing(engine, notice_no: str, source: str = "G2B") -> None:
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no=notice_no,
                title="seeded",
                source=source,
                raw={},
                category="비관련",
                fit_score=0,
                assignee="미배정",
                analysis={},
                status="analyzed",
                created_at=now,
                updated_at=now,
            )
        )


def _make_raw_bid(bid_no: str = "R26X001", bid_seq: str = "000", title: str = "ABB 차단기") -> RawBid:
    return RawBid(
        bid_no=bid_no,
        bid_seq=bid_seq,
        title=title,
        bid_type="goods",
        org_code="010000",
        org_name="조달청",
        base_price="10000000",
        open_date="20260101090000",
        close_date="20260110170000",
        detail_url=None,
        raw={"bidNtceNo": bid_no, "bidNtceNm": title, "ntceInsttNm": "조달청"},
    )


# ─────────────────────────────────────────────────────────────────────────
# 정상 경로
# ─────────────────────────────────────────────────────────────────────────


def test_search_returns_items_with_already_exists_false_by_default(
    client, sqlite_engine, monkeypatch
):
    async def fake_search_single(self, start, end, keyword):
        return [_make_raw_bid("R26X001", "000", "ABB 차단기 22.9kV")]

    monkeypatch.setattr(
        "api.collector.g2b_client.G2BClient.search_single", fake_search_single
    )

    r = client.post("/notices/search", json={"keyword": "ABB"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["notice_no"] == "R26X001-000"
    assert item["title"] == "ABB 차단기 22.9kV"
    assert item["source"] == "G2B"
    assert item["org_name"] == "조달청"
    assert item["base_price"] == 10_000_000
    assert item["already_exists"] is False
    assert item["raw"]["bidNtceNo"] == "R26X001"


def test_search_marks_already_exists_when_db_has_same_source_and_notice_no(
    client, sqlite_engine, monkeypatch
):
    _seed_existing(sqlite_engine, notice_no="R26X001-000", source="G2B")

    async def fake_search_single(self, start, end, keyword):
        return [
            _make_raw_bid("R26X001", "000", "기존 공고"),
            _make_raw_bid("R26X002", "000", "신규 공고"),
        ]

    monkeypatch.setattr(
        "api.collector.g2b_client.G2BClient.search_single", fake_search_single
    )

    r = client.post("/notices/search", json={"keyword": "ABB"})
    assert r.status_code == 200
    by_no = {it["notice_no"]: it for it in r.json()["items"]}
    assert by_no["R26X001-000"]["already_exists"] is True
    assert by_no["R26X002-000"]["already_exists"] is False


def test_search_does_not_match_existing_with_different_source(
    client, sqlite_engine, monkeypatch
):
    # KJEBI 출처로 동일 notice_no가 있어도 G2B 검색에선 already_exists=False
    _seed_existing(sqlite_engine, notice_no="R26X001-000", source="KJEBI")

    async def fake_search_single(self, start, end, keyword):
        return [_make_raw_bid("R26X001", "000")]

    monkeypatch.setattr(
        "api.collector.g2b_client.G2BClient.search_single", fake_search_single
    )

    r = client.post("/notices/search", json={"keyword": "ABB"})
    assert r.status_code == 200
    assert r.json()["items"][0]["already_exists"] is False


def test_search_single_parallelizes_endpoints(monkeypatch):
    """5개 PPSSrch 엔드포인트가 윈도우 내에서 asyncio.gather로 동시 호출되는지.

    각 _fetch_all에 0.3초 sleep을 박고 전체 search_single wall-clock 측정:
      - 순차: 5엔드포인트 × 0.3초 = 1.5초+
      - 병렬: ~0.3초
    여유 두고 < 1.0초로 검증.
    """
    import asyncio
    import time

    from api.collector.g2b_client import G2BClient

    async def slow_fetch_all(self, path, bid_type, start, end, keyword):
        await asyncio.sleep(0.3)
        return []

    monkeypatch.setattr(G2BClient, "_fetch_all", slow_fetch_all)

    async def run():
        from datetime import date as _date

        client = G2BClient.__new__(G2BClient)
        client._key = "dummy"
        return await client.search_single(_date(2026, 1, 1), _date(2026, 1, 10), "kw")

    t0 = time.monotonic()
    result = asyncio.run(run())
    elapsed = time.monotonic() - t0
    assert result == []
    # 순차였다면 1.5초+, 병렬이면 ~0.3초. 1.0초 미만이면 병렬 확정.
    assert elapsed < 1.0, f"search_single appears sequential: {elapsed:.2f}s"


def test_search_single_dedupes_bid_key(monkeypatch):
    """G2BClient.search_single이 (bid_no, bid_seq) 중복을 제거하는지."""
    import asyncio

    from api.collector.g2b_client import G2BClient

    async def fake_fetch_all(self, path, bid_type, start, end, keyword):
        # 매 호출마다 동일 (bid_no, bid_seq) 반환 — 5엔드포인트 × N윈도우 만큼 중복
        return [_make_raw_bid("DUP001", "000")]

    monkeypatch.setattr(G2BClient, "_fetch_all", fake_fetch_all)

    async def run():
        from datetime import date as _date

        client = G2BClient.__new__(G2BClient)
        client._key = "dummy"
        # _client는 _fetch_all를 mock했으므로 필요 없음
        return await client.search_single(_date(2026, 1, 1), _date(2026, 1, 10), "DUP")

    result = asyncio.run(run())
    assert len(result) == 1
    assert result[0].bid_no == "DUP001"


# ─────────────────────────────────────────────────────────────────────────
# 422 검증
# ─────────────────────────────────────────────────────────────────────────


def test_search_rejects_empty_keyword(client):
    r = client.post("/notices/search", json={"keyword": ""})
    assert r.status_code == 422


def test_search_rejects_whitespace_only_keyword(client, monkeypatch):
    # Pydantic min_length=1은 통과하지만 strip 후 빈 문자열은 라우터가 거부.
    r = client.post("/notices/search", json={"keyword": "   "})
    assert r.status_code == 422


def test_search_rejects_inverted_date_range(client):
    r = client.post(
        "/notices/search",
        json={
            "keyword": "ABB",
            "start_date": "2026-06-30T00:00:00",
            "end_date": "2026-06-01T00:00:00",
        },
    )
    assert r.status_code == 422
    assert "after" in r.json()["detail"].lower()


def test_search_rejects_range_exceeding_365_days(client):
    r = client.post(
        "/notices/search",
        json={
            "keyword": "ABB",
            "start_date": "2025-01-01T00:00:00",
            "end_date": "2026-06-01T00:00:00",
        },
    )
    assert r.status_code == 422
    assert "365" in r.json()["detail"]


def test_search_accepts_365_day_range(client, monkeypatch):
    async def fake_search_single(self, start, end, keyword):
        return []

    monkeypatch.setattr(
        "api.collector.g2b_client.G2BClient.search_single", fake_search_single
    )

    # 2026-01-01 ~ 2026-12-31 = 364일 → 경계 통과. 365일도 통과해야 함.
    r = client.post(
        "/notices/search",
        json={
            "keyword": "ABB",
            "start_date": "2026-01-01T00:00:00",
            "end_date": "2026-12-31T00:00:00",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["total_pages"] == 0


# ─────────────────────────────────────────────────────────────────────────
# 502 — G2B 장애
# ─────────────────────────────────────────────────────────────────────────


def test_search_returns_502_on_g2b_failure(client, monkeypatch):
    async def boom(self, start, end, keyword):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(
        "api.collector.g2b_client.G2BClient.search_single", boom
    )

    r = client.post("/notices/search", json={"keyword": "ABB"})
    assert r.status_code == 502
    assert "G2B" in r.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────
# 빈 결과
# ─────────────────────────────────────────────────────────────────────────


def test_search_returns_empty_list_when_no_hits(client, monkeypatch):
    async def fake_search_single(self, start, end, keyword):
        return []

    monkeypatch.setattr(
        "api.collector.g2b_client.G2BClient.search_single", fake_search_single
    )

    r = client.post("/notices/search", json={"keyword": "존재하지않는키워드"})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert body["total_pages"] == 0


# ─────────────────────────────────────────────────────────────────────────
# 페이지네이션
# ─────────────────────────────────────────────────────────────────────────


def _make_n_bids(n: int) -> list:
    """N건의 고유 (bid_no, bid_seq) RawBid 리스트 — 페이지네이션 테스트용."""
    return [
        _make_raw_bid(bid_no=f"R26X{i:03d}", bid_seq="000", title=f"공고 {i}")
        for i in range(n)
    ]


def test_search_paginates_results(client, monkeypatch):
    """120건 mock → page=1: 50건, page=3: 20건. total/total_pages 일관."""
    all_bids = _make_n_bids(120)

    async def fake_search_single(self, start, end, keyword):
        return list(all_bids)

    monkeypatch.setattr(
        "api.collector.g2b_client.G2BClient.search_single", fake_search_single
    )

    # page 1
    r = client.post(
        "/notices/search", json={"keyword": "공고", "page": 1, "page_size": 50}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 50
    assert body["total"] == 120
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert body["total_pages"] == 3
    assert body["items"][0]["notice_no"] == "R26X000-000"

    # page 3 — 마지막 페이지, 20건만
    r = client.post(
        "/notices/search", json={"keyword": "공고", "page": 3, "page_size": 50}
    )
    body = r.json()
    assert len(body["items"]) == 20
    assert body["total"] == 120
    assert body["page"] == 3
    assert body["total_pages"] == 3
    assert body["items"][0]["notice_no"] == "R26X100-000"


def test_search_default_page_size_50(client, monkeypatch):
    """page/page_size 미지정 시 기본값 (page=1, page_size=50)."""
    async def fake_search_single(self, start, end, keyword):
        return _make_n_bids(75)

    monkeypatch.setattr(
        "api.collector.g2b_client.G2BClient.search_single", fake_search_single
    )

    r = client.post("/notices/search", json={"keyword": "공고"})
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert len(body["items"]) == 50
    assert body["total"] == 75
    assert body["total_pages"] == 2


def test_search_page_beyond_total_returns_empty(client, monkeypatch):
    """page=99 → 빈 items + 정확한 total/total_pages (422 아님)."""
    async def fake_search_single(self, start, end, keyword):
        return _make_n_bids(30)

    monkeypatch.setattr(
        "api.collector.g2b_client.G2BClient.search_single", fake_search_single
    )

    r = client.post(
        "/notices/search", json={"keyword": "공고", "page": 99, "page_size": 50}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 30
    assert body["page"] == 99
    assert body["total_pages"] == 1


def test_search_rejects_invalid_pagination(client):
    """page<1 또는 page_size 범위 위반 → Pydantic 422."""
    r = client.post(
        "/notices/search", json={"keyword": "ABB", "page": 0, "page_size": 50}
    )
    assert r.status_code == 422

    r = client.post(
        "/notices/search", json={"keyword": "ABB", "page": 1, "page_size": 0}
    )
    assert r.status_code == 422

    r = client.post(
        "/notices/search", json={"keyword": "ABB", "page": 1, "page_size": 999}
    )
    assert r.status_code == 422


def test_search_already_exists_scoped_to_current_page(
    client, sqlite_engine, monkeypatch
):
    """already_exists DB 조회는 현재 페이지의 notice_no만 대상으로 수행.

    100건 결과 + DB에 R26X000~R26X099 모두 seed.
    page=1,page_size=20 응답 → DB SELECT는 20개 IN 절만 사용해야 함 (성능 회귀 방지).
    """
    # 100건 모두 DB에 미리 seed
    for i in range(100):
        _seed_existing(sqlite_engine, notice_no=f"R26X{i:03d}-000", source="G2B")

    async def fake_search_single(self, start, end, keyword):
        return _make_n_bids(100)

    monkeypatch.setattr(
        "api.collector.g2b_client.G2BClient.search_single", fake_search_single
    )

    # _select_existing_notice_nos 호출 시 인자 캡처
    calls: list[list[str]] = []
    real_select = pipeline._select_existing_notice_nos

    def spy(engine, source, notice_nos):
        calls.append(list(notice_nos))
        return real_select(engine, source=source, notice_nos=notice_nos)

    monkeypatch.setattr(pipeline, "_select_existing_notice_nos", spy)

    r = client.post(
        "/notices/search", json={"keyword": "공고", "page": 1, "page_size": 20}
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 20
    assert all(it["already_exists"] is True for it in body["items"])
    # 핵심: SELECT IN 절은 20개만 — 100개 전체가 아니라 슬라이스된 page만
    assert len(calls) == 1
    assert len(calls[0]) == 20
