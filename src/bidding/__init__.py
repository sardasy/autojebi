"""나라장터 입찰 룰엔진.

- schemas: 입찰 룰/평가 가중치/회사 프로필/결과 Pydantic 모델
- pricing: 복수예가 메커니즘 몬테카를로 시뮬레이션 + 사정율 전략
- eligibility: 적격심사 점수 계산 (납품실적/경영상태/기술능력/신인도)
- decision: 적격심사 + 가격 + 마진 임계를 통합한 의사결정

순수 계산 모듈 — DB/HTTP/파일 I/O 없음. seed 로 재현 가능.
"""
from src.bidding.schemas import (
    TenderRule,
    EvaluationWeights,
    DeliveryRecord,
    CompanyProfile,
    PricingResult,
    EligibilityResult,
    BidDecision,
)
from src.bidding.pricing import simulate_estimated_price, recommend_bid_price
from src.bidding.eligibility import score_eligibility
from src.bidding.decision import (
    PRODUCT_CATEGORY_DEFAULTS,
    auto_select_strategy,
    decide_bid,
)

__all__ = [
    "TenderRule",
    "EvaluationWeights",
    "DeliveryRecord",
    "CompanyProfile",
    "PricingResult",
    "EligibilityResult",
    "BidDecision",
    "simulate_estimated_price",
    "recommend_bid_price",
    "score_eligibility",
    "PRODUCT_CATEGORY_DEFAULTS",
    "auto_select_strategy",
    "decide_bid",
]
