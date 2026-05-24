import pytest
from src.collector.g2b_api import G2BCollector


def test_parse_item_normal():
    collector = G2BCollector()
    item = {
        "bidNtceNo": "20240001",
        "bidNtceNm": "○○변전소 수배전반 교체공사",
        "ntceInsttNm": "한국전력공사",
        "presmptPrce": "500000000",
        "bidClseDt": "2026/06/30 18:00",
        "bidNtceDt": "2026/05/22 09:00",
    }
    result = collector._parse_item(item, "공사")
    assert result is not None
    assert result.source_id == "20240001"
    assert result.estimated_price == 500_000_000


def test_parse_item_missing_fields():
    collector = G2BCollector()
    result = collector._parse_item({}, "공사")
    # source_id가 빈 문자열이어도 파싱은 성공해야 함
    assert result is not None


def test_extract_items_list():
    collector = G2BCollector()
    data = {"response": {"body": {"items": {"item": [{"a": 1}, {"a": 2}]}}}}
    assert len(collector._extract_items(data)) == 2


def test_extract_items_single_dict():
    collector = G2BCollector()
    data = {"response": {"body": {"items": {"item": {"a": 1}}}}}
    assert len(collector._extract_items(data)) == 1


def test_extract_items_empty():
    collector = G2BCollector()
    assert collector._extract_items({}) == []


def test_parse_item_dates_are_utc_aware():
    """G2B API serves KST timestamps; parser must emit timezone-aware UTC."""
    from datetime import timezone

    collector = G2BCollector()
    item = {
        "bidNtceNo": "20240002",
        "bidNtceNm": "테스트",
        "bidClseDt": "2026/06/30 18:00",
        "bidNtceDt": "2026/05/22 09:00",
    }
    result = collector._parse_item(item, "공사")

    assert result.deadline.tzinfo is not None
    assert result.deadline.utcoffset() == timezone.utc.utcoffset(None)
    assert result.deadline.hour == 9  # 18:00 KST → 09:00 UTC

    assert result.announcement_date.tzinfo is not None
    assert result.announcement_date.hour == 0  # 09:00 KST → 00:00 UTC
