"""Typed contracts shared by every decision engine and persistence adapter."""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Any, Generic, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductFamily(StrEnum):
    HIL = "hil"
    SIMULATION_SOFTWARE = "simulation_software"
    SEMICONDUCTOR = "semiconductor"
    FUSE = "fuse"
    CAPACITOR = "capacitor"
    BUSBAR = "busbar"
    SENSOR = "sensor"
    POWER_EQUIPMENT = "power_equipment"
    MIXED = "mixed"
    OTHER = "other"
    IRRELEVANT = "irrelevant"


class Application(StrEnum):
    ESS = "ess"
    HVDC = "hvdc"
    EV = "ev"
    RAILWAY = "railway"
    RENEWABLE = "renewable"
    GRID = "grid"
    INDUSTRIAL = "industrial"
    DEFENSE = "defense"
    RESEARCH = "research"
    OTHER = "other"


class CompanyRelevance(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    IRRELEVANT = "irrelevant"


class BidPriority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class RoutingTarget(StrEnum):
    AUTO_PROCESS = "auto_process"
    LLM_VERIFY = "llm_verify"
    HUMAN_REVIEW = "human_review"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoticeDecisionInput(StrictModel):
    notice_no: str = Field(min_length=1, max_length=200)
    title: str = Field(default="", max_length=2000)
    organization: str = Field(default="", max_length=1000)
    body: str = Field(default="", max_length=100_000)
    source_fields: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_content(self) -> Self:
        if not self.title.strip() and not self.body.strip():
            raise ValueError("title or body is required")
        return self


class CompanyContext(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=5000)
    positive_signals: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class RoutingThresholds(StrictModel):
    auto_process_min_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    llm_verify_min_confidence: float = Field(default=0.70, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> Self:
        if self.auto_process_min_confidence < self.llm_verify_min_confidence:
            raise ValueError("auto_process threshold must be >= llm_verify threshold")
        return self


class CompanyPolicy(StrictModel):
    schema_version: Literal[1] = 1
    policy_version: str = Field(min_length=1, max_length=100)
    company: CompanyContext
    product_families: dict[ProductFamily, str] = Field(min_length=2)
    applications: dict[Application, str] = Field(min_length=2)
    relevance_levels: dict[CompanyRelevance, str] = Field(min_length=2)
    priority_levels: dict[BidPriority, str] = Field(min_length=2)
    routing: RoutingThresholds = Field(default_factory=RoutingThresholds)


DecisionLabel = TypeVar("DecisionLabel", bound=StrEnum)


class DecisionValue(StrictModel, Generic[DecisionLabel]):
    value: DecisionLabel
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[str, float] = Field(min_length=1)

    @model_validator(mode="after")
    def selected_value_is_in_distribution(self) -> Self:
        if self.value.value not in self.probabilities:
            raise ValueError("selected value is missing from probabilities")
        if any(
            not isfinite(probability) or probability < 0.0 or probability > 1.0
            for probability in self.probabilities.values()
        ):
            raise ValueError("probabilities must be between 0 and 1")
        return self


class EngineDecision(StrictModel):
    engine_name: str = Field(min_length=1, max_length=100)
    model_version: str = Field(min_length=1, max_length=200)
    policy_version: str = Field(min_length=1, max_length=100)
    product_family: DecisionValue[ProductFamily]
    application: DecisionValue[Application]
    company_relevance: DecisionValue[CompanyRelevance]
    bid_priority: DecisionValue[BidPriority]

    @property
    def confidences(self) -> dict[str, float]:
        return {
            "product_family": self.product_family.confidence,
            "application": self.application.confidence,
            "company_relevance": self.company_relevance.confidence,
            "bid_priority": self.bid_priority.confidence,
        }


class RoutingDecision(StrictModel):
    target: RoutingTarget
    overall_confidence: float = Field(ge=0.0, le=1.0)
    limiting_signal: str
    reason: str


class DecisionEvaluation(StrictModel):
    notice_no: str
    input_hash: str = Field(min_length=64, max_length=64)
    decision: EngineDecision
    routing: RoutingDecision
