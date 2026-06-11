"""api/grading/summarizer.py 단위 테스트.

anthropic.Anthropic을 mock해서 tool_use 정상/누락/예외 케이스 검증.
LLM 실패 시 fallback이 동작하는지 확인.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from api.grading.schemas import FitSummary, ScoreBreakdown
from api.grading.summarizer import _fallback_summary, summarize_fit
from api.llm.schemas import ElecSpec
from api.sku.schemas import AbbSku, SkuMatch


def _mk_breakdown(total: float = 0.7, qual: float = 0.7, price: float = 0.7) -> ScoreBreakdown:
    return ScoreBreakdown(
        spec=0.7, qualification=qual, price=price,
        weights={"spec": 0.5, "qualification": 0.2, "price": 0.3},
        total=total,
    )


def _mk_match() -> SkuMatch:
    return SkuMatch(
        score=0.85,
        sku=AbbSku(sku_id="ABB-X", name="RESIBLOC 1000kVA", category="변압기", description="d"),
    )


def _make_tool_stream(payload: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "summarize_fit"
    block.input = payload
    message = MagicMock()
    message.content = [block]
    stream = MagicMock()
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)
    stream.get_final_message = MagicMock(return_value=message)
    return stream


def test_summarize_returns_llm_result_on_tool_use():
    payload = {
        "reason": "변압기 22.9kV 1000kVA 공고로 ABB RESIBLOC와 적합합니다.",
        "recommended_sku_id": "ABB-X",
        "risk_note": None,
    }
    client = MagicMock()
    client.messages.stream.return_value = _make_tool_stream(payload)

    with patch("api.grading.summarizer.anthropic.Anthropic", return_value=client):
        result = summarize_fit(
            "변압기 구매",
            ElecSpec(product_category="변압기", rated_voltage_kv=22.9, rated_power_kva=1000.0),
            [_mk_match()],
            _mk_breakdown(),
            ["결격 사유 없음"],
            "공고 30,000,000원 ∈ typical 25,000,000~60,000,000원",
        )

    assert isinstance(result, FitSummary)
    assert result.reason.startswith("변압기")
    assert result.recommended_sku_id == "ABB-X"


def test_summarize_falls_back_when_no_tool_use_block():
    message = MagicMock()
    message.content = []
    stream = MagicMock()
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)
    stream.get_final_message = MagicMock(return_value=message)
    client = MagicMock()
    client.messages.stream.return_value = stream

    with patch("api.grading.summarizer.anthropic.Anthropic", return_value=client):
        result = summarize_fit(
            "변압기 구매",
            ElecSpec(product_category="변압기", rated_voltage_kv=22.9, rated_power_kva=1000.0),
            [_mk_match()],
            _mk_breakdown(),
            ["결격 사유 없음"],
            "in-range",
        )

    # fallback이 ABB RESIBLOC 인용
    assert "ABB RESIBLOC" in result.reason or "ABB" in result.reason
    assert result.recommended_sku_id == "ABB-X"


def test_summarize_falls_back_on_anthropic_exception():
    with patch(
        "api.grading.summarizer.anthropic.Anthropic",
        side_effect=Exception("api down"),
    ):
        result = summarize_fit(
            "변압기 구매",
            ElecSpec(product_category="변압기", rated_power_kva=1000.0),
            [],
            _mk_breakdown(),
            ["x"],
            "y",
        )

    # 매칭 없으면 sku 인용은 일반 표현
    assert "ABB 제품" in result.reason
    assert result.recommended_sku_id is None


def test_fallback_risk_note_on_low_qual():
    summary = _fallback_summary(
        ElecSpec(product_category="변압기", rated_voltage_kv=22.9),
        [],
        _mk_breakdown(qual=0.3),
        ["계약방법 '수의계약' — 지명 명단 확인 필요 (-0.5)"],
        "neutral",
    )
    assert summary.risk_note is not None
    assert "수의" in summary.risk_note
