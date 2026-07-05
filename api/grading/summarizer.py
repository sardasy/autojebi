"""공고 적합 사유 한 줄 요약 — Claude tool_use("summarize_fit").

abb-bid-pipeline의 summarizer.py에서 이식. settings.anthropic_model 사용 (M2 이미 도입).
LLM 실패 시 룰 기반 fallback으로 발송 자체를 막지 않는다.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from api.config import settings
from api.grading.schemas import FitSummary, ScoreBreakdown
from api.llm.schemas import ElecSpec
from api.sku.schemas import SkuMatch

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
당신은 ABB Korea 영업 분석가입니다. 한국 공공조달 공고가 ABB 제품 라인업에
얼마나 적합한지 한 줄(1~2 문장)로 요약합니다.

## 입력
- 공고 제목
- 추출된 전기 사양 (ElecSpec)
- Top SKU 매칭 결과 (이름 + 유사도 점수)
- 점수 분해 (spec / qualification / price 각 0~1)
- 자격 휴리스틱 메모, 예가 휴리스틱 메모

## 출력 규칙
- `summarize_fit` 도구를 반드시 호출해 JSON 반환.
- `reason`: "OO공고는 OO 사유로 ABB OO 제품에 적합합니다." 형식 한국어 존대.
  - 사양 핵심값(전압·용량·차단용량) 중 1개 이상 인용.
  - 점수 숫자 자체는 본문에 적지 않음.
- `recommended_sku_id`: top1 매칭의 sku_id (없으면 null).
- `risk_note`: 자격/예가에 결격 사유 있을 때만 한 줄. 없으면 null.

## 톤
- 영업 의사결정 한 줄. 미사여구·과장 금지.
"""

_TOOL_DEF: dict[str, Any] = {
    "name": "summarize_fit",
    "description": "Generate a one-line Korean rationale describing why this bid fits ABB.",
    "input_schema": FitSummary.model_json_schema(),
}


def summarize_fit(
    bid_title: str,
    spec: ElecSpec,
    top_matches: list[SkuMatch],
    breakdown: ScoreBreakdown,
    qual_notes: list[str],
    price_note: str,
) -> FitSummary:
    user_msg = _build_user_message(bid_title, spec, top_matches, breakdown, qual_notes, price_note)
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=512,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[_TOOL_DEF],
            tool_choice={"type": "tool", "name": "summarize_fit"},
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            message = stream.get_final_message()

        for block in message.content:
            if block.type == "tool_use" and block.name == "summarize_fit":
                return FitSummary.model_validate(block.input)

        log.warning("[summarizer] tool_use 블록 없음 → fallback 사용")
        return _fallback_summary(spec, top_matches, breakdown, qual_notes, price_note)
    except Exception as exc:  # noqa: BLE001 — LLM 경계: 어떤 실패든 fallback으로 흡수
        log.warning("[summarizer] Claude 호출 실패(%s) → fallback 사용", exc)
        return _fallback_summary(spec, top_matches, breakdown, qual_notes, price_note)


def _build_user_message(
    bid_title: str,
    spec: ElecSpec,
    top_matches: list[SkuMatch],
    breakdown: ScoreBreakdown,
    qual_notes: list[str],
    price_note: str,
) -> str:
    spec_dump = spec.model_dump_json(exclude_none=True)
    matches_summary = "\n".join(
        f"- {m.sku.sku_id} {m.sku.name} (유사도 {m.score:.3f})"
        for m in top_matches[:3]
    ) or "(매칭 없음)"
    return (
        f"## 공고 제목\n{bid_title}\n\n"
        f"## 추출 사양\n{spec_dump}\n\n"
        f"## Top SKU 매칭\n{matches_summary}\n\n"
        f"## 점수\nspec={breakdown.spec:.3f}, "
        f"qualification={breakdown.qualification:.3f}, price={breakdown.price:.3f}, "
        f"total={breakdown.total:.3f}\n\n"
        f"## 자격 메모\n" + "\n".join(f"- {n}" for n in qual_notes) + "\n\n"
        f"## 예가 메모\n{price_note}\n\n"
        "위 정보를 바탕으로 `summarize_fit` 도구를 호출해 적합 사유를 요약하십시오."
    )


def _fallback_summary(
    spec: ElecSpec,
    top_matches: list[SkuMatch],
    breakdown: ScoreBreakdown,
    qual_notes: list[str],
    price_note: str,
) -> FitSummary:
    top = top_matches[0] if top_matches else None
    sku_phrase = f"ABB {top.sku.name}" if top else "ABB 제품"
    cat = spec.product_category or "전기 기자재"
    rating_bits: list[str] = []
    if spec.rated_voltage_kv:
        rating_bits.append(f"{spec.rated_voltage_kv}kV")
    if spec.rated_power_kva:
        rating_bits.append(f"{spec.rated_power_kva}kVA")
    if spec.rated_power_kw:
        rating_bits.append(f"{spec.rated_power_kw}kW")
    if spec.rated_current_a:
        rating_bits.append(f"{spec.rated_current_a}A")
    rating_str = " ".join(rating_bits) or "사양 미상"

    reason = f"{cat} {rating_str} 공고로 {sku_phrase}와 적합합니다."

    risk: str | None = None
    if breakdown.qualification < 0.7 or breakdown.price < 0.5:
        bits = [n for n in qual_notes if "0.0" in n or "-" in n]
        if bits:
            risk = bits[0]
        elif "공고" in price_note and (
            "미달" in price_note or "초과" in price_note or "<" in price_note or ">" in price_note
        ):
            risk = price_note

    return FitSummary(
        reason=reason,
        recommended_sku_id=top.sku.sku_id if top else None,
        risk_note=risk,
    )
