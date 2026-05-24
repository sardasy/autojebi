"""src/bidding/decision.py 테스트."""
import pytest

from src.bidding.decision import (
    PRODUCT_CATEGORY_DEFAULTS,
    auto_select_strategy,
    decide_bid,
)
from src.bidding.schemas import (
    CompanyProfile,
    DeliveryRecord,
    EligibilityResult,
    EvaluationWeights,
    TenderRule,
)


def _strong_profile() -> CompanyProfile:
    """통과 보장 + 가산점 충분."""
    return CompanyProfile(
        recent_3y_delivery_records=[
            DeliveryRecord(agency="KEPCO", product_class="IGBT", amount=300_000_000, year=2024),
        ],
        credit_grade="AAA",
        debt_ratio=0.3,
        iso_certifications=["ISO 9001", "ISO 14001"],
        technical_staff_count=10,
        has_koshams=True,
        is_sme=True,
    )


def _weak_profile() -> CompanyProfile:
    """가격 만점에도 통과 불가."""
    return CompanyProfile(
        recent_3y_delivery_records=[],
        credit_grade="CCC",
        debt_ratio=0.9,
        iso_certifications=[],
        technical_staff_count=0,
        has_severe_accident=True,
    )


def test_eligibility_fail_short_circuit():
    """적격심사 불가 → pricing 계산 생략."""
    decision = decide_bid(
        rule=TenderRule(base_price=100_000_000),
        weights=EvaluationWeights(),
        profile=_weak_profile(),
        product_class="IGBT",
        product_category="DEFAULT",
        tender_amount=100_000_000,
        unit_cost=80_000_000,
    )
    assert decision.recommend is False
    assert decision.pricing_detail is None
    assert decision.strategy == "none"
    assert decision.bid_price == 0.0
    assert any("적격심사" in r for r in decision.reasons)


def test_low_margin_rejection():
    """적격은 통과하지만 마진이 제품군 최소 미달 → recommend=False."""
    # bid = 100M * 1.0 * 0.87745 = 87.745M (balanced 전략 가정)
    # unit_cost 87M → margin ≈ 0.86%, DEFAULT.min_margin=10% 미달
    decision = decide_bid(
        rule=TenderRule(base_price=100_000_000),
        weights=EvaluationWeights(),
        profile=_strong_profile(),
        product_class="IGBT",
        product_category="DEFAULT",
        tender_amount=100_000_000,
        unit_cost=87_000_000,
        strategy_override="balanced",
    )
    assert decision.recommend is False
    assert any("마진 미달" in r for r in decision.reasons)
    # 마진 미달이어도 pricing 은 계산됨 (단락 아님)
    assert decision.pricing_detail is not None


def test_strategy_auto_selection():
    """auto_select_strategy: max_price_score_needed 구간별로 정확히 분기."""
    def make(needed: float) -> EligibilityResult:
        # 다른 필드는 임의값
        return EligibilityResult(
            delivery_performance=20.0,
            financial_status=20.0,
            technical_capability=8.0,
            credibility=0.0,
            subtotal_without_price=85.0 - needed,
            max_price_score_needed=needed,
            passable=True,
        )

    assert auto_select_strategy(make(10.0)) == "safe"
    assert auto_select_strategy(make(14.99)) == "safe"
    assert auto_select_strategy(make(15.0)) == "balanced"
    assert auto_select_strategy(make(20.0)) == "balanced"
    assert auto_select_strategy(make(21.99)) == "balanced"
    assert auto_select_strategy(make(22.0)) == "aggressive"
    assert auto_select_strategy(make(30.0)) == "aggressive"


def test_reasons_in_korean():
    decision = decide_bid(
        rule=TenderRule(base_price=100_000_000),
        weights=EvaluationWeights(),
        profile=_strong_profile(),
        product_class="IGBT",
        product_category="DEFAULT",
        tender_amount=100_000_000,
        unit_cost=50_000_000,
    )
    joined = " ".join(decision.reasons)
    has_korean = any(0xAC00 <= ord(c) <= 0xD7A3 for c in joined)
    assert has_korean, f"reasons 에 한국어 문자가 없음: {decision.reasons}"
    assert len(decision.reasons) >= 2


def test_strategy_override_respected():
    decision = decide_bid(
        rule=TenderRule(base_price=100_000_000),
        weights=EvaluationWeights(),
        profile=_strong_profile(),
        product_class="IGBT",
        product_category="DEFAULT",
        tender_amount=100_000_000,
        unit_cost=50_000_000,
        strategy_override="aggressive",
    )
    assert decision.strategy == "aggressive"
    assert any("강제 지정" in r for r in decision.reasons)


def test_product_category_min_margin_applied():
    """PLECS_LICENSE (min_margin=0.20) 는 더 까다로운 마진 기준."""
    # bid ≈ 87.745M @ balanced. unit=70M → margin ≈ 25%.
    # PLECS_LICENSE min_margin=0.20 → 통과
    decision = decide_bid(
        rule=TenderRule(base_price=100_000_000),
        weights=EvaluationWeights(),
        profile=_strong_profile(),
        product_class="IGBT",
        product_category="PLECS_LICENSE",
        tender_amount=100_000_000,
        unit_cost=70_000_000,
        strategy_override="balanced",
    )
    assert decision.recommend is True

    # unit=80M → margin ≈ 9.7% < 20% → 미달
    decision2 = decide_bid(
        rule=TenderRule(base_price=100_000_000),
        weights=EvaluationWeights(),
        profile=_strong_profile(),
        product_class="IGBT",
        product_category="PLECS_LICENSE",
        tender_amount=100_000_000,
        unit_cost=80_000_000,
        strategy_override="balanced",
    )
    assert decision2.recommend is False


def test_default_category_used_when_unknown():
    """알 수 없는 product_category 면 DEFAULT 적용."""
    decision = decide_bid(
        rule=TenderRule(base_price=100_000_000),
        weights=EvaluationWeights(),
        profile=_strong_profile(),
        product_class="IGBT",
        product_category="NEVER_HEARD_OF_THIS",
        tender_amount=100_000_000,
        unit_cost=50_000_000,
        strategy_override="balanced",
    )
    # DEFAULT.min_margin=0.10, bid≈87.7M, unit=50M → margin ≈75% → 추천
    assert decision.recommend is True
    assert PRODUCT_CATEGORY_DEFAULTS["DEFAULT"]["min_margin"] == pytest.approx(0.10)
