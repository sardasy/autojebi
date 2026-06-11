"""G2BClient 동기 단위 테스트 — 실제 API 호출 없음.

비동기 fetch_qualifications 테스트는 M3 (그레이딩 도입) 시점까지 보류.
"""

from __future__ import annotations

from api.collector.g2b_client import (
    G2BClient,
    _normalize_service_key,
    keyword_queries,
    keyword_variants,
    match_all_tokens,
    match_raw,
)


def _make_item(**kwargs: object) -> dict:
    base = {
        "bidNtceNo": "20240101001",
        "bidNtceOrd": "00",
        "bidNtceNm": "ABB 변압기 구매",
        "dminsttCd": "010000",
        "ntceInsttNm": "조달청",
        "presmptPrce": "50000000",
        "bidNtceDt": "20240101090000",
        "bidClseDt": "20240110170000",
        "bidNtceUrl": None,
    }
    base.update(kwargs)
    return base


class TestParse:
    def test_single_item(self) -> None:
        body = {"response": {"body": {"items": {"item": _make_item()}}}}
        bids = G2BClient._parse(body, "goods")
        assert len(bids) == 1
        assert bids[0].bid_no == "20240101001"
        assert bids[0].bid_type == "goods"

    def test_multi_items(self) -> None:
        body = {
            "response": {
                "body": {
                    "items": {
                        "item": [
                            _make_item(),
                            _make_item(bidNtceNo="20240101002"),
                        ]
                    }
                }
            }
        }
        bids = G2BClient._parse(body, "service")
        assert len(bids) == 2

    def test_empty_items(self) -> None:
        body = {"response": {"body": {"items": None}}}
        assert G2BClient._parse(body, "goods") == []

    def test_missing_bid_no(self) -> None:
        body = {"response": {"body": {"items": {"item": {"bidNtceNo": ""}}}}}
        assert G2BClient._parse(body, "goods") == []


class TestHelpers:
    def test_parse_price_comma(self) -> None:
        assert G2BClient.parse_price("50,000,000") == 50_000_000

    def test_parse_price_none(self) -> None:
        assert G2BClient.parse_price(None) is None

    def test_parse_datetime_valid(self) -> None:
        result = G2BClient.parse_datetime("20240101090000")
        assert result == "2024-01-01T09:00:00+09:00"

    def test_parse_datetime_dash_format(self) -> None:
        # G2B 실 응답 포맷 — 'YYYY-MM-DD HH:MM:SS'
        result = G2BClient.parse_datetime("2024-01-01 09:00:00")
        assert result == "2024-01-01T09:00:00+09:00"

    def test_parse_datetime_date_only_compact(self) -> None:
        assert G2BClient.parse_datetime("20240101") == "2024-01-01T00:00:00+09:00"

    def test_parse_datetime_date_only_dashed(self) -> None:
        assert G2BClient.parse_datetime("2024-01-01") == "2024-01-01T00:00:00+09:00"

    def test_parse_datetime_short(self) -> None:
        assert G2BClient.parse_datetime("2024") is None

    def test_parse_datetime_empty(self) -> None:
        assert G2BClient.parse_datetime("") is None
        assert G2BClient.parse_datetime(None) is None

    def test_normalize_org_type_central(self) -> None:
        assert G2BClient.normalize_org_type("조달청") == "central"

    def test_normalize_org_type_education(self) -> None:
        assert G2BClient.normalize_org_type("서울대학교") == "education"

    def test_normalize_region(self) -> None:
        assert G2BClient.normalize_region("경기도청") == "경기"
        assert G2BClient.normalize_region("조달청") is None

    def test_make_detail_url(self) -> None:
        url = G2BClient.make_detail_url("20240101001", "00")
        assert "bidno=20240101001" in url
        assert "bidSeq=00" in url


class TestKeywordVariants:
    def test_empty(self) -> None:
        assert keyword_variants("") == []
        assert keyword_variants("   ") == []

    def test_short_returns_self_only(self) -> None:
        assert keyword_variants("abc") == ["abc"]

    def test_long_returns_self_only(self) -> None:
        assert keyword_variants("a" * 13) == ["a" * 13]

    def test_already_has_space(self) -> None:
        assert keyword_variants("제어기 시험장치") == ["제어기 시험장치"]

    def test_generates_space_variants(self) -> None:
        out = keyword_variants("제어기시험장치")
        assert "제어기시험장치" in out
        assert "제어기 시험장치" in out
        assert len(out) <= 4

    def test_trims_whitespace(self) -> None:
        assert "제어기시험장치" in keyword_variants("  제어기시험장치 ")


class TestKeywordQueries:
    def test_phrase_adds_token_queries_for_order_insensitive_search(self) -> None:
        out = keyword_queries("실시간 전력전자 시뮬레이션 장비")
        assert out[0] == "실시간 전력전자 시뮬레이션 장비"
        assert "시뮬레이션" in out
        assert "전력전자" not in out
        assert "장비" not in out

    def test_single_keyword_keeps_existing_variants(self) -> None:
        out = keyword_queries("제어기시험장치")
        assert "제어기시험장치" in out
        assert "제어기 시험장치" in out


class TestMatchRaw:
    def test_title_hit(self) -> None:
        raw = {"bidNtceNm": "강원본부 휴대용 변압기 시험기 1대"}
        ok, field = match_raw(raw, ["변압기"])
        assert ok is True and field == "bidNtceNm"

    def test_filename_hit(self) -> None:
        raw = {"bidNtceNm": "기타", "ntceSpecFileNm3": "제어기시험장치 사양서.hwp"}
        ok, field = match_raw(raw, ["제어기시험장치"])
        assert ok is True and field == "ntceSpecFileNm3"

    def test_content_hit(self) -> None:
        raw = {"rmrkCntnts": "본 사업은 제어기시험장치 도입을 포함합니다."}
        ok, field = match_raw(raw, ["제어기시험장치"])
        assert ok is True and field == "rmrkCntnts"

    def test_no_match(self) -> None:
        raw = {"bidNtceNm": "도로 포장 공사"}
        ok, field = match_raw(raw, ["변압기"])
        assert ok is False and field is None

    def test_one_of_many_needles(self) -> None:
        raw = {"bidNtceNm": "제어기 시험장치 구매"}
        ok, field = match_raw(raw, ["없는단어", "제어기 시험장치"])
        assert ok is True and field == "bidNtceNm"

    def test_empty_needles(self) -> None:
        ok, _ = match_raw({"bidNtceNm": "x"}, [])
        assert ok is False


class TestMatchAllTokens:
    def test_matches_reordered_title_tokens(self) -> None:
        raw = {"bidNtceNm": "전력전자 실시간 시뮬레이션 장비 구매"}
        assert match_all_tokens(raw, "실시간 전력전자 시뮬레이션 장비") is True

    def test_matches_tokens_across_title_and_attachment(self) -> None:
        raw = {
            "bidNtceNm": "전력전자 장비 구매",
            "ntceSpecFileNm1": "실시간 시뮬레이션 규격서.hwp",
        }
        assert match_all_tokens(raw, "실시간 전력전자 시뮬레이션 장비") is True

    def test_rejects_missing_token(self) -> None:
        raw = {"bidNtceNm": "전력전자 시뮬레이션 장비 구매"}
        assert match_all_tokens(raw, "실시간 전력전자 시뮬레이션 장비") is False


class TestNormalizeServiceKey:
    def test_raw_passthrough(self) -> None:
        assert _normalize_service_key("abc+def/=") == "abc+def/="

    def test_url_encoded_decoded(self) -> None:
        encoded = "abc%2Bdef%2F%3D"
        assert _normalize_service_key(encoded) == "abc+def/="
