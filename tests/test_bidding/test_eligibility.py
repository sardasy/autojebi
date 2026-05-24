"""src/bidding/eligibility.py 테스트."""
import pytest

from src.bidding.eligibility import score_eligibility
from src.bidding.schemas import (
    CompanyProfile,
    DeliveryRecord,
    EvaluationWeights,
)


def _profile(**overrides) -> CompanyProfile:
    base = dict(
        recent_3y_delivery_records=[],
        credit_grade="BBB",
        debt_ratio=0.4,
        iso_certifications=[],
        technical_staff_count=0,
    )
    base.update(overrides)
    return CompanyProfile(**base)


def test_credit_grade_mapping():
    """AAA / AA / A 변형 + BBB / BB 변형 모두 root 매핑."""
    w = EvaluationWeights()  # financial_status=30
    cases = [
        ("AAA", 30.0),
        ("AA+", 30.0),   # AA root → 1.00
        ("AA-", 30.0),
        ("A",  30.0 * 0.98),
        ("A-", 30.0 * 0.98),
        ("BBB", 30.0 * 0.95),
        ("BBB+", 30.0 * 0.95),
        ("BB+", 30.0 * 0.90),
        ("CCC", 30.0 * 0.80),  # 미지 → default
    ]
    for grade, expected in cases:
        p = _profile(credit_grade=grade)
        r = score_eligibility(p, w, "X", 100_000_000)
        assert r.financial_status == pytest.approx(expected), (
            f"grade={grade!r}: got {r.financial_status}, expected {expected}"
        )


def test_severe_accident_deduction():
    """중대재해 발생 → 신인도 -3."""
    p = _profile(has_severe_accident=True)
    r = score_eligibility(p, EvaluationWeights(), "X", 100_000_000)
    assert r.credibility == pytest.approx(-3.0)


def test_combined_credibility_bonus():
    """모든 가산점 조합 (중소기업, 부품 국산화 포함)."""
    p = _profile(
        has_severe_accident=False,
        has_koshams=True,
        converted_to_regular=True,
        parts_localization=True,
        is_sme=True,
    )
    r = score_eligibility(p, EvaluationWeights(), "X", 100_000_000)
    # +1 +1.5 +1 = 3.5
    assert r.credibility == pytest.approx(3.5)


def test_parts_localization_requires_sme():
    """중소기업이 아니면 부품 국산화 가산점 미적용."""
    p = _profile(parts_localization=True, is_sme=False)
    r = score_eligibility(p, EvaluationWeights(), "X", 100_000_000)
    assert r.credibility == pytest.approx(0.0)


def test_pass_threshold_calculation():
    """가격 만점 가정 시 통과 가능성 판단."""
    w = EvaluationWeights()  # pass_threshold=85, bid_price=30

    # 통과 가능: AAA + 실적 100% + ISO 2개 → 30 + 30 + 0.9*10 = 69. 69+30 >= 85.
    good = _profile(
        recent_3y_delivery_records=[
            DeliveryRecord(agency="X", product_class="A", amount=100_000_000, year=2024),
        ],
        credit_grade="AAA",
        iso_certifications=["ISO 9001", "ISO 14001"],
    )
    r1 = score_eligibility(good, w, "A", 100_000_000)
    assert r1.passable is True

    # 통과 불가: 실적 0 + 미지등급 + ISO 0 + 중대재해
    # delivery 30*0.8=24, fin 30*0.8=24, tech 10*0.7=7, cred=-3 → 52. 52+30=82 < 85.
    bad = _profile(
        credit_grade="CCC",
        has_severe_accident=True,
    )
    r2 = score_eligibility(bad, w, "A", 100_000_000)
    assert r2.passable is False
    assert r2.subtotal_without_price == pytest.approx(52.0)


def test_iso_cap_at_3():
    """ISO 인증 4개 이상이어도 기술능력은 만점(=0.7+0.1*3=1.0)."""
    p = _profile(
        credit_grade="AAA",
        iso_certifications=["ISO 9001", "ISO 14001", "ISO 27001", "ISO 45001", "OHSAS 18001"],
    )
    r = score_eligibility(p, EvaluationWeights(), "X", 100_000_000)
    assert r.technical_capability == pytest.approx(10.0)

    # 정확히 3개여도 동일
    p3 = _profile(
        credit_grade="AAA",
        iso_certifications=["ISO 9001", "ISO 14001", "ISO 27001"],
    )
    r3 = score_eligibility(p3, EvaluationWeights(), "X", 100_000_000)
    assert r3.technical_capability == pytest.approx(10.0)


def test_delivery_ratio_stepping():
    """실적 비율 경계값에서 단계 점수 정확히 변경되는지."""
    w = EvaluationWeights()

    def perf(amount: float) -> float:
        rec = DeliveryRecord(agency="X", product_class="A", amount=amount, year=2024)
        p = _profile(recent_3y_delivery_records=[rec])
        return score_eligibility(p, w, "A", 100_000_000).delivery_performance

    assert perf(100_000_000) == pytest.approx(30.0)         # ratio 1.0
    assert perf(50_000_000) == pytest.approx(30.0 * 0.95)   # ratio 0.5
    assert perf(25_000_000) == pytest.approx(30.0 * 0.90)   # ratio 0.25
    assert perf(10_000_000) == pytest.approx(30.0 * 0.80)   # ratio 0.1


def test_delivery_filters_by_product_class():
    """다른 품목군 실적은 합산되지 않는다."""
    p = _profile(
        recent_3y_delivery_records=[
            DeliveryRecord(agency="X", product_class="OTHER", amount=500_000_000, year=2024),
        ],
    )
    r = score_eligibility(p, EvaluationWeights(), "A", 100_000_000)
    # ratio = 0 → 0.80
    assert r.delivery_performance == pytest.approx(30.0 * 0.80)
