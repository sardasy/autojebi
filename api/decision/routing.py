"""Code-owned confidence policy. Routing is not a final bid/no-bid decision."""

from __future__ import annotations

from api.decision.models import (
    EngineDecision,
    RoutingDecision,
    RoutingTarget,
    RoutingThresholds,
)


def route_by_confidence(
    decision: EngineDecision,
    thresholds: RoutingThresholds,
) -> RoutingDecision:
    limiting_signal, confidence = min(decision.confidences.items(), key=lambda item: item[1])
    if confidence >= thresholds.auto_process_min_confidence:
        target = RoutingTarget.AUTO_PROCESS
    elif confidence >= thresholds.llm_verify_min_confidence:
        target = RoutingTarget.LLM_VERIFY
    else:
        target = RoutingTarget.HUMAN_REVIEW
    return RoutingDecision(
        target=target,
        overall_confidence=confidence,
        limiting_signal=limiting_signal,
        reason=f"minimum signal confidence {confidence:.4f} ({limiting_signal})",
    )
