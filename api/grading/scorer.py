"""세 축(사양·자격·예가) 점수 + 가중합. 순수 함수 — LLM/HTTP 호출 없음.

abb-bid-pipeline의 scorer.py에서 이식. import 경로만 app → api로 조정.
qualification.score_qualification은 라이브 API 인자 제거된 단순화 버전 사용.
"""

from __future__ import annotations

import json
from decimal import Decimal

from api.config import settings
from api.grading.price_table import lookup_price_range, normalize_category
from api.grading.qualification import score_qualification
from api.grading.schemas import ScoreBreakdown
from api.llm.schemas import ElecSpec
from api.sku.schemas import SkuMatch

_SPEC_NOISE_FLOOR = 0.4


def score_spec(top: SkuMatch | None) -> float:
    if top is None:
        return 0.0
    s = float(top.score)
    if s < _SPEC_NOISE_FLOOR:
        return 0.0
    return max(0.0, min(1.0, s))


def score_price(
    spec: ElecSpec,
    base_price: Decimal | int | float | None,
    raw_json: str | None = None,
) -> tuple[float, str]:
    """공고 base_price가 카테고리 typical 단가 × quantity 범위에 들어가는지 평가."""
    if base_price is None:
        return 0.5, "예가 정보 없음 → 중립 0.5"

    cat = normalize_category(spec.product_category)
    if cat is None:
        return 0.5, "product_category 미지 → 중립 0.5"

    if spec.quantity is None:
        return 0.5, "quantity 미지 → 중립 0.5 (수량 오인 시 점수 폭락 방지)"

    rng = lookup_price_range(spec)
    if rng is None:
        return 0.5, f"카테고리 '{cat}' typical 단가 미정 → 중립 0.5"

    qty = max(1, spec.quantity)
    lo, hi = rng[0] * qty, rng[1] * qty
    p = float(base_price)

    src = _price_source_label(raw_json)
    src_suffix = f" (출처: {src})" if src else ""

    if lo <= p <= hi:
        return 1.0, f"공고 {p:,.0f}원 ∈ typical {lo:,.0f}~{hi:,.0f}원{src_suffix}"
    if p < lo:
        ratio = p / lo if lo > 0 else 0.0
        return max(0.0, ratio * 0.7), (
            f"공고 {p:,.0f}원 < typical 하한 {lo:,.0f}원{src_suffix}"
        )
    ratio = hi / p if p > 0 else 0.0
    return max(0.0, ratio * 0.7), (
        f"공고 {p:,.0f}원 > typical 상한 {hi:,.0f}원{src_suffix}"
    )


def _price_source_label(raw_json: str | None) -> str | None:
    if not raw_json:
        return None
    try:
        raw = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if raw.get("presmptPrce"):
        return "presmptPrce (추정가)"
    if raw.get("asignBdgtAmt"):
        return "asignBdgtAmt (배정예산)"
    return None


def combine(
    spec_s: float,
    qual_s: float,
    price_s: float,
    weights: dict[str, float] | None = None,
    hard_gate_qual_zero: bool | None = None,
) -> ScoreBreakdown:
    w = weights or settings.grade_weights
    gate = (
        settings.grade_hard_gate_qual_zero
        if hard_gate_qual_zero is None
        else hard_gate_qual_zero
    )

    if gate and qual_s == 0.0:
        total = 0.0
    else:
        total = spec_s * w["spec"] + qual_s * w["qualification"] + price_s * w["price"]
        total = max(0.0, min(1.0, total))

    return ScoreBreakdown(
        spec=spec_s,
        qualification=qual_s,
        price=price_s,
        weights=w,
        total=total,
    )


__all__ = ["score_spec", "score_qualification", "score_price", "combine"]
