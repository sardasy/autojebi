"""Thin adapter around the optional official TypeSafe Python SDK."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Protocol, TypeVar

from api.decision.engine import (
    DecisionEngine,
    DecisionEngineResponseError,
    DecisionEngineUnavailable,
)
from api.decision.models import (
    Application,
    BidPriority,
    CompanyPolicy,
    CompanyRelevance,
    DecisionValue,
    EngineDecision,
    NoticeDecisionInput,
    ProductFamily,
)


class SystemOneClient(Protocol):
    def system_one(
        self,
        state: dict[str, Any],
        questions: Mapping[str, dict[str, Any]],
        *,
        model: str,
    ) -> Any: ...

    def close(self) -> None: ...


LabelT = TypeVar("LabelT", bound=StrEnum)


class JevEngine(DecisionEngine):
    """Map company taxonomy to four Jev Choice questions in one request."""

    def __init__(
        self,
        *,
        client: SystemOneClient | None = None,
        model: str = "jev-latest",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._client = client
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    @property
    def engine_name(self) -> str:
        return "jev"

    def _create_client(self) -> SystemOneClient:
        try:
            from typesafe_sdk import RetryPolicy, TypeSafeClient
        except ImportError as exc:
            raise DecisionEngineUnavailable(
                'Jev support is not installed; run pip install -e ".[jev]"'
            ) from exc
        options: dict[str, Any] = {"model": self._model, "timeout": self._timeout,
                                   "retry": RetryPolicy(max_retries=0)}
        if self._api_key:
            options["api_key"] = self._api_key
        return TypeSafeClient(**options)

    def decide(self, notice: NoticeDecisionInput, policy: CompanyPolicy) -> EngineDecision:
        client = self._client or self._create_client()
        owns_client = self._client is None
        try:
            response = client.system_one(
                state=self._state(notice, policy),
                questions=self._questions(policy),
                model=self._model,
            )
        finally:
            if owns_client:
                client.close()
        choices = getattr(response, "choices", None)
        if not isinstance(choices, Mapping):
            raise DecisionEngineResponseError("Jev response has no choices mapping")
        response_model = str(getattr(response, "model", self._model))
        return EngineDecision(
            engine_name=self.engine_name,
            model_version=response_model,
            policy_version=policy.policy_version,
            product_family=self._choice_value(
                choices.get("product_family"), ProductFamily, "product_family"
            ),
            application=self._choice_value(choices.get("application"), Application, "application"),
            company_relevance=self._choice_value(
                choices.get("company_relevance"), CompanyRelevance, "company_relevance"
            ),
            bid_priority=self._choice_value(
                choices.get("bid_priority"), BidPriority, "bid_priority"
            ),
        )

    @staticmethod
    def _state(notice: NoticeDecisionInput, policy: CompanyPolicy) -> dict[str, Any]:
        return {
            "notice": notice.model_dump(mode="json"),
            "company": policy.company.model_dump(mode="json"),
            "policy_version": policy.policy_version,
        }

    @staticmethod
    def _criteria(values: Mapping[StrEnum, str]) -> dict[str, str]:
        return {key.value: description for key, description in values.items()}

    @classmethod
    def _questions(cls, policy: CompanyPolicy) -> dict[str, dict[str, Any]]:
        return {
            "product_family": {
                "type": "choice",
                "instructions": "Select the single best product family for this notice.",
                "criteria": cls._criteria(policy.product_families),
            },
            "application": {
                "type": "choice",
                "instructions": "Select the primary application domain for this notice.",
                "criteria": cls._criteria(policy.applications),
            },
            "company_relevance": {
                "type": "choice",
                "instructions": (
                    "Assess semantic fit with the supplied company policy. "
                    "This is not permission to bid."
                ),
                "criteria": cls._criteria(policy.relevance_levels),
            },
            "bid_priority": {
                "type": "choice",
                "instructions": (
                    "Assign a triage priority from public notice content and company fit. "
                    "Do not infer legal eligibility or approve submission."
                ),
                "criteria": cls._criteria(policy.priority_levels),
            },
        }

    @staticmethod
    def _choice_value(
        answer: Any,
        enum_type: type[LabelT],
        question_name: str,
    ) -> DecisionValue[LabelT]:
        if answer is None:
            raise DecisionEngineResponseError(f"missing Jev answer: {question_name}")
        try:
            value = enum_type(str(answer.choice))
            confidence = float(answer.confidence)
            probabilities = {str(key): float(item) for key, item in answer.probabilities.items()}
            return DecisionValue[enum_type](
                value=value,
                confidence=confidence,
                probabilities=probabilities,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise DecisionEngineResponseError(
                f"invalid Jev choice answer: {question_name}"
            ) from exc
