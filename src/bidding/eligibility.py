"""적격심사 점수 계산기.

종합 점수 = 납품실적(30) + 경영상태(30) + 기술능력(10) + 가격(30) + 신인도(가감점)
통과 기준: pass_threshold (통상 85점) 이상

신인도 (2026.1 개정 반영):
- 중대재해 발생          -3
- KOSHA-MS 인증           +1
- 정규직 전환 실적        +1.5
- 부품 국산화 (중소만)    +1
"""
from __future__ import annotations

from src.bidding.schemas import (
    CompanyProfile,
    EvaluationWeights,
    EligibilityResult,
)


# 경영상태 신용등급 → 가중치 (등급 root 기준; +/- 접미사 제거 후 lookup)
_CREDIT_GRADE_MULTIPLIER: dict[str, float] = {
    "AAA": 1.00,
    "AA": 1.00,
    "A": 0.98,
    "BBB": 0.95,
    "BB": 0.90,
}
_CREDIT_GRADE_DEFAULT = 0.80


def _grade_multiplier(grade: str) -> float:
    """'AA+', 'A-' 등에서 +/- 제거한 root 로 매핑."""
    root = grade.rstrip("+-").strip().upper()
    return _CREDIT_GRADE_MULTIPLIER.get(root, _CREDIT_GRADE_DEFAULT)


def _delivery_ratio_score_pct(ratio: float) -> float:
    """납품실적 비율에 따른 단계 점수.

    ratio = (동일 품목군 최근 3년 실적 합계) / 공고 추정금액
    """
    if ratio >= 1.0:
        return 1.00
    if ratio >= 0.5:
        return 0.95
    if ratio >= 0.25:
        return 0.90
    return 0.80


def _credibility_bonus(profile: CompanyProfile) -> float:
    """신인도 가감점 (음수 가능)."""
    score = 0.0
    if profile.has_severe_accident:
        score -= 3.0
    if profile.has_koshams:
        score += 1.0
    if profile.converted_to_regular:
        score += 1.5
    if profile.parts_localization and profile.is_sme:
        score += 1.0
    return score


def score_eligibility(
    profile: CompanyProfile,
    weights: EvaluationWeights,
    tender_product_class: str,
    tender_amount: float,
) -> EligibilityResult:
    """가격 항목 제외한 모든 적격심사 점수 계산.

    Returns 의 ``passable`` 은 "가격 항목을 만점 받는다고 가정" 한 가능성 판단.
    실제 가격 점수는 응찰 후 결정되므로 별도 계산.
    """
    # 1) 납품실적
    matching = [r for r in profile.recent_3y_delivery_records
                if r.product_class == tender_product_class]
    total_amount = sum(r.amount for r in matching)
    ratio = (total_amount / tender_amount) if tender_amount > 0 else 0.0
    perf_pct = _delivery_ratio_score_pct(ratio)
    perf = weights.delivery_performance * perf_pct

    # 2) 경영상태
    fin_pct = _grade_multiplier(profile.credit_grade)
    fin = weights.financial_status * fin_pct

    # 3) 기술능력: ISO 인증 개수에 따른 배수 (최대 3개까지 카운트)
    iso_count = min(len(profile.iso_certifications), 3)
    tech_pct = 0.7 + 0.1 * iso_count
    tech = weights.technical_capability * tech_pct

    # 4) 신인도
    cred = _credibility_bonus(profile)

    subtotal = perf + fin + tech + cred
    # 가격 만점을 가정한 통과 가능성
    max_needed = weights.pass_threshold - subtotal
    passable = (subtotal + weights.bid_price) >= weights.pass_threshold

    return EligibilityResult(
        delivery_performance=perf,
        financial_status=fin,
        technical_capability=tech,
        credibility=cred,
        subtotal_without_price=subtotal,
        max_price_score_needed=max_needed,
        passable=passable,
    )
