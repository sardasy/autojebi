"""입찰 룰엔진 Pydantic v2 스키마.

용어:
- base_price (기초금액): 발주처가 산정한 기초 금액
- 복수예가: 기초금액 ±2% 범위에서 추출한 N 개의 후보 가격
- 예정가격 (expected price): 무작위 4 개의 산술평균
- 낙찰하한율 (nakchal_lower_rate): 통상 87.745% — 공고별 가변
- 사정율: 우리가 base_price 에 곱하는 전략 계수 (aggressive/balanced/safe)
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# 입찰 룰 / 평가 가중치
# ---------------------------------------------------------------------------

class TenderRule(BaseModel):
    """공고별 복수예가/낙찰 규칙."""

    base_price: float = Field(..., gt=0, description="기초금액 (원)")
    price_range_pct: float = Field(default=0.02, ge=0, le=0.1, description="복수예가 변동률 (±)")
    n_candidates: int = Field(default=15, ge=2, description="추출되는 복수예가 개수")
    n_picked: int = Field(default=4, ge=1, description="예정가격 산출 시 무작위 선정 개수")
    nakchal_lower_rate: float = Field(
        default=0.87745, gt=0, le=1,
        description="낙찰하한율 (통상 87.745% — 공고별 가변)",
    )


class EvaluationWeights(BaseModel):
    """적격심사 항목별 만점.

    합계가 통상 100 이지만 공고별로 다를 수 있으므로 강제하지 않는다.
    """

    delivery_performance: float = Field(default=30.0, ge=0)
    technical_capability: float = Field(default=10.0, ge=0)
    financial_status: float = Field(default=30.0, ge=0)
    credibility: float = Field(default=0.0, description="가산점 합계 한도 (실제 부여는 schema 외부)")
    bid_price: float = Field(default=30.0, ge=0, description="가격 평점 만점")
    pass_threshold: float = Field(default=85.0, ge=0, description="종합 통과 임계")


# ---------------------------------------------------------------------------
# 회사 프로필
# ---------------------------------------------------------------------------

class DeliveryRecord(BaseModel):
    """납품 실적 1건."""

    agency: str = Field(..., description="발주기관")
    product_class: str = Field(..., description="물품 분류 (적격심사 매칭 키)")
    amount: float = Field(..., ge=0, description="계약금액 (원)")
    year: int = Field(..., ge=2000, le=2100)


class CompanyProfile(BaseModel):
    """우리 회사의 입찰 자격/실적 스냅샷."""

    recent_3y_delivery_records: list[DeliveryRecord] = Field(default_factory=list)
    credit_grade: str = Field(default="BBB", description="신용등급 (AAA/AA+/AA-/A/BBB/BB/...)")
    debt_ratio: float = Field(default=0.5, ge=0, description="부채비율")
    iso_certifications: list[str] = Field(default_factory=list, description="ISO 등 인증 목록")
    technical_staff_count: int = Field(default=0, ge=0, description="기술인력 수")

    # 신인도 (2026.1 개정 반영)
    has_severe_accident: bool = Field(default=False, description="중대재해 발생 (-3)")
    has_koshams: bool = Field(default=False, description="KOSHA-MS 인증 보유 (+1)")
    converted_to_regular: bool = Field(default=False, description="정규직 전환 실적 (+1.5)")
    parts_localization: bool = Field(default=False, description="부품 국산화 실적 (+1, 중소기업만)")
    is_sme: bool = Field(default=True, description="중소기업 여부 (parts_localization 가산 조건)")


# ---------------------------------------------------------------------------
# 결과 모델
# ---------------------------------------------------------------------------

class PricingResult(BaseModel):
    """recommend_bid_price() 결과."""

    bid_price: float = Field(..., description="추천 응찰가")
    expected_price_mean: float = Field(..., description="예정가격 분포의 평균")
    expected_price_p5: float = Field(..., description="예정가격 5 백분위수")
    expected_price_p95: float = Field(..., description="예정가격 95 백분위수")
    nakchal_lower_mean: float = Field(..., description="낙찰하한가 분포 평균 (= expected_price * 하한율)")
    win_zone_probability: float = Field(
        ..., ge=0, le=1,
        description="bid_price ∈ [낙찰하한가, 예정가격] 조건을 만족하는 시뮬레이션 비율",
    )


class EligibilityResult(BaseModel):
    """score_eligibility() 결과."""

    delivery_performance: float = Field(..., description="납품실적 점수")
    financial_status: float = Field(..., description="경영상태 점수")
    technical_capability: float = Field(..., description="기술능력 점수")
    credibility: float = Field(..., description="신인도 가감점 (음수 가능)")
    subtotal_without_price: float = Field(..., description="가격 제외 소계")
    max_price_score_needed: float = Field(
        ..., description="통과를 위해 가격 항목에서 받아야 하는 최소 점수 (음수면 이미 통과)",
    )
    passable: bool = Field(
        ..., description="가격 만점을 받았을 때 통과 가능 여부 (subtotal + bid_price >= threshold)",
    )


class BidDecision(BaseModel):
    """decide_bid() 통합 결정."""

    model_config = ConfigDict(arbitrary_types_allowed=False)

    recommend: bool = Field(..., description="응찰 추천 여부")
    strategy: str = Field(..., description="선택된 사정율 전략 (aggressive/balanced/safe/none)")
    bid_price: float = Field(..., description="추천 응찰가 (short-circuit 시 0)")
    expected_margin_pct: float = Field(..., description="예상 마진율 (bid - unit_cost)/unit_cost")
    win_zone_probability: float = Field(..., ge=0, le=1)
    eligibility_score: float = Field(..., description="적격심사 가격 제외 소계")
    pricing_detail: Optional[PricingResult] = None
    eligibility_detail: EligibilityResult
    reasons: list[str] = Field(default_factory=list, description="판단 근거 (한국어)")
