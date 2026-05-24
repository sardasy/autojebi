"""PR 3: RegexExtractor + DualExtractor + korean_amount_to_int."""
import pytest

from src.llm.extraction_validators import (
    DualExtractor,
    RegexExtractor,
    ValidationConflict,
    korean_amount_to_int,
)
from src.llm.structured_output import BidSpecs, BidSummaryOutput


# ---------------------------------------------------------------------------
# korean_amount_to_int
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("일금 일억오천만원정", 150_000_000),
    ("일억오천만", 150_000_000),
    ("壹億伍仟萬", 150_000_000),
    ("一億五千萬", 150_000_000),
    ("이백오십", 250),
    ("십", 10),
    ("이천오백만원", 25_000_000),
    ("일조이백억", 1_020_000_000_000),  # 1e12 + 200*1e8
    ("", None),
    ("아무거나", None),
])
def test_korean_amount(text, expected):
    assert korean_amount_to_int(text) == expected


# ---------------------------------------------------------------------------
# RegexExtractor
# ---------------------------------------------------------------------------

@pytest.fixture
def rex():
    return RegexExtractor()


def test_regex_base_price_comma_format(rex):
    text = "공고: 변전소 교체\n기초금액 : 1,234,567,890 원"
    assert rex.extract_base_price(text) == 1_234_567_890.0


def test_regex_base_price_korean(rex):
    text = "기초금액 일금 일억오천만원정"
    assert rex.extract_base_price(text) == 150_000_000.0


def test_regex_base_price_no_unit(rex):
    text = "기초금액: 500,000,000"
    assert rex.extract_base_price(text) == 500_000_000.0


def test_regex_nakchal_rate_percent(rex):
    text = "낙찰하한가율: 87.745%"
    assert rex.extract_nakchal_rate(text) == 0.87745


def test_regex_nakchal_rate_already_decimal(rex):
    text = "낙찰 하한율 0.87745"
    assert rex.extract_nakchal_rate(text) == 0.87745


def test_regex_deadline_iso_format(rex):
    text = "입찰마감일시: 2026-03-15 14:00"
    dt = rex.extract_deadline(text)
    assert dt is not None
    assert dt.year == 2026 and dt.month == 3 and dt.day == 15
    assert dt.hour == 14 and dt.minute == 0


def test_regex_deadline_korean_format(rex):
    text = "입찰 마감 2026년 3월 15일 14시 30분"
    dt = rex.extract_deadline(text)
    assert dt is not None
    assert dt.year == 2026 and dt.day == 15
    assert dt.hour == 14 and dt.minute == 30


def test_regex_deadline_date_only(rex):
    text = "입찰마감일: 2026-03-15"
    dt = rex.extract_deadline(text)
    assert dt is not None
    assert dt.hour == 0  # 시간 미지정 → 자정


def test_regex_classification(rex):
    text = "조달청 물품분류번호: 26111703"
    assert rex.extract_classification(text) == "26111703"


def test_regex_tender_type(rex):
    assert rex.extract_tender_type("일반경쟁입찰로 진행") == "일반경쟁"
    assert rex.extract_tender_type("협상에 의한 계약") == "협상에의한계약"
    assert rex.extract_tender_type("다수공급자계약(MAS)") == "MAS"
    assert rex.extract_tender_type("관련 키워드 없음") is None


def test_regex_eval_method(rex):
    assert rex.extract_evaluation_method("적격심사 방식") == "적격심사"
    assert rex.extract_evaluation_method("종합평가 100점 기준") == "종합평가"


def test_regex_direct_mfg_and_loa(rex):
    text = "직접생산증명을 제출. 제조사 위임장(LoA) 또한 제출 가능."
    assert rex.extract_direct_mfg(text) is True
    assert rex.extract_loa_accepted(text) is True

    text2 = "특별 요구사항 없음."
    assert rex.extract_direct_mfg(text2) is False
    assert rex.extract_loa_accepted(text2) is False


def test_loa_does_not_false_positive_on_proxy_submission():
    """PR α 회귀: '대리인 제출 시 위임장 및 신분증' 같은 *입찰 자연인 위임* 은
    공급사 LoA 와 무관하므로 False 여야 함. 실제 한국에너지공과대학교 공고에서 발견.
    """
    rex = RegexExtractor()
    cases_false = [
        "⑥ 대리인 제출 시 : 위임장 및 신분증 사본(또는 재직증명서) 각 1부",
        "위임장 제출 (입찰참가 대리권)",
        "대리인이 위임장을 지참",
    ]
    for c in cases_false:
        assert rex.extract_loa_accepted(c) is False, f"false positive: {c!r}"

    cases_true = [
        "제조사 위임장(LoA) 제출 가능",
        "Letter of Authorization 필요",
        "판매 위임장 첨부",
        "공급사 위임장 필요",
        "대리점 위임장 제출",
    ]
    for c in cases_true:
        assert rex.extract_loa_accepted(c) is True, f"missed true: {c!r}"


# ---------------------------------------------------------------------------
# DualExtractor — LLM 모킹
# ---------------------------------------------------------------------------

class _StubLLMGateway:
    """summarize_bid 가 반환할 BidSummaryOutput 을 미리 지정."""

    def __init__(self, specs_dict: dict, summary: str = "stub"):
        self._out = BidSummaryOutput(
            summary=summary,
            specs=BidSpecs.model_validate(specs_dict),
        )

    async def summarize_bid(self, bid_content: str, attachment_text: str = ""):
        return self._out


@pytest.mark.asyncio
async def test_dual_no_conflict_when_values_agree():
    text = "기초금액: 100,000,000원\n낙찰하한가율: 87.745%\n물품분류번호: 26111703"
    llm = _StubLLMGateway({
        "공고명": "x", "발주기관": "y",
        "기초금액": 100_000_000, "낙찰하한율": 0.87745,
        "조달청물품분류번호": "26111703",
    })
    specs, conflicts = await DualExtractor().extract_with_validation(text, llm)
    assert conflicts == []
    assert specs.기초금액 == 100_000_000.0
    assert specs.낙찰하한율 == 0.87745


@pytest.mark.asyncio
async def test_dual_no_conflict_within_tolerance():
    """0.5% 차이 — 임계 1% 미만이라 conflict 아님."""
    text = "기초금액: 100,000,000원"  # regex = 100M
    llm = _StubLLMGateway({
        "공고명": "x", "발주기관": "y",
        "기초금액": 99_500_000,  # LLM = 99.5M → 0.5% 오차
    })
    specs, conflicts = await DualExtractor().extract_with_validation(text, llm)
    assert all(c.field != "기초금액" for c in conflicts)
    # LLM 값 유지 (regex 와 close enough)
    assert specs.기초금액 == 99_500_000.0


@pytest.mark.asyncio
async def test_dual_critical_amount_diff_above_1pct():
    text = "기초금액: 100,000,000원"
    llm = _StubLLMGateway({
        "공고명": "x", "발주기관": "y",
        "기초금액": 95_000_000,  # 5% 오차 → critical
    })
    specs, conflicts = await DualExtractor().extract_with_validation(text, llm)
    critical = [c for c in conflicts if c.severity == "critical"]
    assert any(c.field == "기초금액" for c in critical)
    # regex 가 우선 (100M)
    assert specs.기초금액 == 100_000_000.0


@pytest.mark.asyncio
async def test_dual_rate_diff_above_threshold():
    text = "낙찰하한가율: 87.745%"  # regex = 0.87745
    llm = _StubLLMGateway({
        "공고명": "x", "발주기관": "y",
        "낙찰하한율": 0.85,  # 0.0274 차이 > 0.001 → critical
    })
    specs, conflicts = await DualExtractor().extract_with_validation(text, llm)
    assert any(c.field == "낙찰하한율" and c.severity == "critical" for c in conflicts)
    assert specs.낙찰하한율 == 0.87745


@pytest.mark.asyncio
async def test_dual_classification_exact_mismatch():
    text = "물품분류번호: 26111703"
    llm = _StubLLMGateway({
        "공고명": "x", "발주기관": "y",
        "조달청물품분류번호": "26111702",  # 한 자리 차이 — 분류 다름
    })
    specs, conflicts = await DualExtractor().extract_with_validation(text, llm)
    assert any(c.field == "조달청물품분류번호" and c.severity == "critical" for c in conflicts)
    assert specs.조달청물품분류번호 == "26111703"  # regex 우선


@pytest.mark.asyncio
async def test_dual_fills_from_regex_when_llm_misses():
    """LLM 이 None 으로 둔 필드를 regex 가 보완."""
    text = "기초금액: 500,000,000원\n물품분류번호: 12345678"
    llm = _StubLLMGateway({
        "공고명": "x", "발주기관": "y",
        # 기초금액, 분류번호 누락
    })
    specs, conflicts = await DualExtractor().extract_with_validation(text, llm)
    assert conflicts == []  # 한쪽만 있으면 conflict 아님
    assert specs.기초금액 == 500_000_000.0
    assert specs.조달청물품분류번호 == "12345678"


@pytest.mark.asyncio
async def test_dual_warning_for_tender_type_mismatch():
    """입찰방식 불일치는 warning 만."""
    text = "협상에 의한 계약 진행"  # regex → 협상에의한계약
    llm = _StubLLMGateway({
        "공고명": "x", "발주기관": "y",
        "입찰방식": "일반경쟁",  # LLM 잘못 추출
    })
    specs, conflicts = await DualExtractor().extract_with_validation(text, llm)
    warnings = [c for c in conflicts if c.severity == "warning"]
    assert any(c.field == "입찰방식" for c in warnings)
    # warning 은 LLM 값 유지
    assert specs.입찰방식 == "일반경쟁"


def test_conflict_to_dict_jsonable():
    """ValidationConflict.to_dict() — JSONB 저장 가능한 형태."""
    import json
    from datetime import datetime

    c = ValidationConflict(
        field="입찰마감",
        regex_value=datetime(2026, 3, 15, 14, 0),
        llm_value="2026-03-16 14:00",
        severity="critical",
    )
    d = c.to_dict()
    json.dumps(d)  # serializable
    assert d["regex_value"] == "2026-03-15T14:00:00"
    assert d["severity"] == "critical"
