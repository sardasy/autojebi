"""Replaceable engine boundary; Jev, LLM, and local engines implement this contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from api.decision.models import CompanyPolicy, EngineDecision, NoticeDecisionInput


class DecisionEngineError(RuntimeError):
    """Base error for unavailable engines and invalid provider responses."""


class DecisionEngineUnavailable(DecisionEngineError):
    """The selected engine cannot run because configuration or a dependency is missing."""


class DecisionEngineResponseError(DecisionEngineError):
    """The provider returned an incomplete or contract-breaking response."""


class DecisionEngine(ABC):
    """Synchronous decision interface used by the Day 1 pipeline.

    OpenAI, Claude, or local implementations should translate their native response into
    ``EngineDecision``. Engine failures must raise; they must never become an irrelevant decision.
    """

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Stable provider name stored with each decision."""

    @abstractmethod
    def decide(self, notice: NoticeDecisionInput, policy: CompanyPolicy) -> EngineDecision:
        """Evaluate one notice without applying workflow routing or side effects."""
