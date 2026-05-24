"""적격심사 + 가격 + 마진을 통합한 응찰 의사결정."""
from __future__ import annotations
from typing import Optional

from src.bidding.eligibility import score_eligibility
from src.bidding.pricing import recommend_bid_price
from src.bidding.schemas import (
    BidDecision,
    CompanyProfile,
    EligibilityResult,
    EvaluationWeights,
    PricingResult,
    TenderRule,
)


# 제품군별 기본 전략 편향 + 최소 마진 임계
PRODUCT_CATEGORY_DEFAULTS: dict[str, dict] = {
    "ABB_IGBT_MODULE":  {"strategy_bias": "aggressive", "min_margin": 0.05},
    "ABB_SCR":          {"strategy_bias": "aggressive", "min_margin": 0.06},
    "PLECS_LICENSE":    {"strategy_bias": "safe",       "min_margin": 0.20},
    "TYPHOON_HIL":      {"strategy_bias": "balanced",   "min_margin": 0.15},
    "DEFAULT":          {"strategy_bias": "balanced",   "min_margin": 0.10},
}


def auto_select_strategy(eligibility: EligibilityResult) -> str:
    """적격심사 가격점수 여유에 따른 전략 자동 선택.

    max_price_score_needed 가 작을수록 (= 비가격 점수가 높을수록) 굳이 가격을 낮춰서
    가격 점수를 더 받을 필요가 없다 → 마진 확보 전략 (safe).
    반대로 비가격 점수가 약하면 가격으로 만회 → aggressive.
    """
    margin = eligibility.max_price_score_needed
    if margin < 15:
        return "safe"
    if margin < 22:
        return "balanced"
    return "aggressive"


def decide_bid(
    rule: TenderRule,
    weights: EvaluationWeights,
    profile: CompanyProfile,
    product_class: str,
    product_category: str,
    tender_amount: float,
    unit_cost: float,
    strategy_override: Optional[str] = None,
) -> BidDecision:
    """전체 파이프라인:
    적격심사 → 통과 시 전략 선택 → 가격 계산 → 마진 검증 → 추천 여부.

    적격심사 통과 불가능하면 가격 계산을 생략 (short-circuit).
    """
    reasons: list[str] = []

    # 1) 적격심사 — 통과 불가면 즉시 종결
    eligibility = score_eligibility(profile, weights, product_class, tender_amount)
    if not eligibility.passable:
        reasons.append(
            f"적격심사 통과 불가능: 비가격 소계 {eligibility.subtotal_without_price:.2f} + "
            f"가격 만점 {weights.bid_price:.2f} < 임계 {weights.pass_threshold:.2f}"
        )
        return BidDecision(
            recommend=False,
            strategy="none",
            bid_price=0.0,
            expected_margin_pct=0.0,
            win_zone_probability=0.0,
            eligibility_score=eligibility.subtotal_without_price,
            pricing_detail=None,
            eligibility_detail=eligibility,
            reasons=reasons,
        )

    # 2) 전략 선택
    cat_defaults = PRODUCT_CATEGORY_DEFAULTS.get(
        product_category, PRODUCT_CATEGORY_DEFAULTS["DEFAULT"],
    )
    strategy_bias = cat_defaults["strategy_bias"]
    min_margin = float(cat_defaults["min_margin"])

    if strategy_override:
        strategy = strategy_override
        reasons.append(f"전략 강제 지정: {strategy}")
    else:
        strategy = auto_select_strategy(eligibility)
        reasons.append(
            f"전략 자동 선택: {strategy} "
            f"(가격점수 여유 {eligibility.max_price_score_needed:.2f}점)"
        )

    if strategy != strategy_bias:
        reasons.append(f"제품군 {product_category} 기본 권장은 {strategy_bias}")

    # 3) 가격 시뮬레이션
    pricing: PricingResult = recommend_bid_price(rule, strategy=strategy)

    # 4) 마진 검증
    if unit_cost <= 0:
        margin_pct = 0.0
        reasons.append("단가 정보 없음 — 마진 평가 불가")
        margin_ok = False
    else:
        margin_pct = (pricing.bid_price - unit_cost) / unit_cost
        margin_ok = margin_pct > min_margin
        if margin_ok:
            reasons.append(
                f"마진 충족: {margin_pct * 100:.2f}% > 제품군 최소 {min_margin * 100:.2f}%"
            )
        else:
            reasons.append(
                f"마진 미달: {margin_pct * 100:.2f}% ≤ 제품군 최소 {min_margin * 100:.2f}%"
            )

    reasons.append(f"낙찰존 진입 확률 {pricing.win_zone_probability * 100:.2f}%")

    recommend = bool(eligibility.passable and margin_ok)

    return BidDecision(
        recommend=recommend,
        strategy=strategy,
        bid_price=pricing.bid_price,
        expected_margin_pct=margin_pct,
        win_zone_probability=pricing.win_zone_probability,
        eligibility_score=eligibility.subtotal_without_price,
        pricing_detail=pricing,
        eligibility_detail=eligibility,
        reasons=reasons,
    )
