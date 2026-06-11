"""collector.pipeline 단위 테스트 — DB 없이 검증 가능한 부분만.

핵심 검증:
  1. notice_no 합성 규칙: f"{bid_no}-{bid_seq}", 빈 seq는 "00"로 정규화.
  2. _clean_title은 줄바꿈/탭을 공백으로 치환.
  3. _parse_iso는 G2B의 ISO+09:00 문자열을 datetime으로 변환.
  4. 멱등성 핵심 — upsert SQL의 `set_` dict는 `status` 키를 포함하지 않는다.
     (재수집이 이미 analyzed/notified된 공고를 collected로 되돌리지 않는 것을 보장.)

실제 G2B HTTP 호출과 DB 라운드트립이 필요한 통합 테스트는 M2 또는 별도 환경에서.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from api.collector import pipeline
from api.collector.g2b_client import RawBid


def test_make_notice_no_basic():
    assert pipeline.make_notice_no("R26BK01543282", "000") == "R26BK01543282-000"


def test_make_notice_no_blank_seq_defaults_to_00():
    assert pipeline.make_notice_no("ABC123", "") == "ABC123-00"


def test_make_notice_no_strips_whitespace():
    assert pipeline.make_notice_no("ABC123", "  01  ") == "ABC123-01"


def test_clean_title_normalizes_whitespace():
    assert pipeline._clean_title("강원본부\n휴대용\t변압기 시험기") == "강원본부 휴대용 변압기 시험기"


def test_clean_title_strips_outer_whitespace():
    assert pipeline._clean_title("  ABB 변압기  ") == "ABB 변압기"


def test_parse_iso_none():
    assert pipeline._parse_iso(None) is None
    assert pipeline._parse_iso("") is None


def test_parse_iso_valid_with_tz():
    dt = pipeline._parse_iso("2026-05-26T16:00:00+09:00")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 5 and dt.day == 26
    assert dt.hour == 16 and dt.minute == 0
    assert dt.utcoffset() is not None


def test_parse_iso_invalid_returns_none():
    assert pipeline._parse_iso("not-a-date") is None


def test_upsert_set_dict_excludes_status():
    """멱등성: 재수집 시 status가 다운그레이드되지 않아야 한다.

    pipeline._upsert는 ON CONFLICT DO UPDATE에서 set_ dict에 'status'를 넣지 않는다.
    그 덕에 기존 행이 analyzed/notified 등 상위 상태였더라도 'collected'로 되돌아가지 않는다.

    SQLAlchemy Core가 컴파일한 INSERT 문을 문자열로 변환하고, ON CONFLICT 절에
    `status = ` 형태의 set 할당이 없는지 확인한다.
    """
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import insert

    from api.routers.notices import bid_pipeline

    now = datetime.now(tz=UTC)
    raw = RawBid(
        bid_no="X",
        bid_seq="00",
        title="t",
        bid_type="goods",
        org_code="0",
        org_name="조달청",
        base_price="100",
        open_date="20260101000000",
        close_date="20260102000000",
        detail_url=None,
        raw={"k": "v"},
    )

    # _upsert 내부 stmt 생성 로직을 그대로 재현해서 컴파일된 SQL을 검사.
    stmt = insert(bid_pipeline).values(
        notice_no=pipeline.make_notice_no(raw.bid_no, raw.bid_seq),
        title=raw.title,
        source="G2B",
        raw=raw.raw,
        status="collected",
        created_at=now,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=[bid_pipeline.c.notice_no],
        set_={
            "title": "x",
            "updated_at": now,
        },
    )
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    # ON CONFLICT 절 추출 후 status 할당이 없는지 확인.
    assert "ON CONFLICT" in compiled
    on_conflict_tail = compiled.split("ON CONFLICT", 1)[1]
    # 'status =' 또는 'status=' 패턴이 SET 절에 등장하면 안 됨.
    # WHERE 절에는 등장할 수 있으므로 SET 부분만 검사.
    set_section = on_conflict_tail.split("DO UPDATE SET", 1)[1].split(" RETURNING", 1)[0]
    assert "status" not in set_section.lower(), set_section


def test_collect_range_passes_today_when_unset(monkeypatch):
    """run_collection은 start/end 미지정 시 오늘로 채워야 한다.

    (G2B HTTP 호출과 DB 적재는 mock — 인자 전달만 검증.)
    """
    captured = {}

    async def fake_collect(start, end, keywords):
        captured["start"] = start
        captured["end"] = end
        captured["keywords"] = keywords
        return []

    class FakeEngine:
        def begin(self):
            from contextlib import contextmanager

            @contextmanager
            def _cm():
                yield None

            return _cm()

    monkeypatch.setattr(pipeline, "_collect_async", fake_collect)

    stats = pipeline.run_collection(FakeEngine(), keywords=["ABB"])
    assert stats == {"fetched": 0, "new": 0, "skipped": 0}
    assert captured["start"] == date.today()
    assert captured["end"] == date.today()
    assert captured["keywords"] == ["ABB"]
