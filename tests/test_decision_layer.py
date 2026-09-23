from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from api.db.tables import bid_pipeline, metadata
from api.decision.engine import DecisionEngine
from api.decision.engines import JevEngine
from api.decision.models import (
    Application,
    BidPriority,
    CompanyPolicy,
    CompanyRelevance,
    DecisionValue,
    EngineDecision,
    NoticeDecisionInput,
    ProductFamily,
    RoutingTarget,
)
from api.decision.policy import CompanyPolicyLoadError, load_company_policy
from api.decision.service import DecisionService, decision_input_hash
from api.decision.storage import save_evaluation
from api.decision.tables import notice_decisions


def _policy() -> CompanyPolicy:
    return CompanyPolicy.model_validate(
        {
            "policy_version": "test-v1",
            "company": {"name": "Test", "summary": "Power electronics"},
            "product_families": {"hil": "HIL", "other": "Other"},
            "applications": {"hvdc": "HVDC", "other": "Other"},
            "relevance_levels": {"high": "Direct fit", "irrelevant": "No fit"},
            "priority_levels": {"high": "Prompt", "none": "None"},
            "routing": {
                "auto_process_min_confidence": 0.90,
                "llm_verify_min_confidence": 0.70,
            },
        }
    )


def _notice() -> NoticeDecisionInput:
    return NoticeDecisionInput(
        notice_no="TEST-001",
        title="HVDC HIL simulator",
        organization="Test lab",
        body="Controller verification system",
    )


def _value(enum_value, confidence: float):
    return DecisionValue(
        value=enum_value,
        confidence=confidence,
        probabilities={enum_value.value: confidence, "other": 1 - confidence},
    )


class FixedEngine(DecisionEngine):
    def __init__(self, confidence: float) -> None:
        self.confidence = confidence

    @property
    def engine_name(self) -> str:
        return "fixed"

    def decide(self, notice, policy) -> EngineDecision:
        del notice
        return EngineDecision(
            engine_name=self.engine_name,
            model_version="fixed-v1",
            policy_version=policy.policy_version,
            product_family=_value(ProductFamily.HIL, self.confidence),
            application=_value(Application.HVDC, self.confidence),
            company_relevance=_value(CompanyRelevance.HIGH, self.confidence),
            bid_priority=_value(BidPriority.HIGH, self.confidence),
        )


def test_example_company_policy_loads() -> None:
    root = Path(__file__).resolve().parent.parent
    policy = load_company_policy(root / "config" / "company.example.yaml")
    assert policy.policy_version == "autojebi-day1-v1"
    assert ProductFamily.HIL in policy.product_families


def test_invalid_threshold_order_is_rejected(tmp_path: Path) -> None:
    policy_file = tmp_path / "company.yaml"
    policy_file.write_text(
        """
policy_version: bad
company: {name: Test, summary: Test}
product_families: {hil: HIL, other: Other}
applications: {hvdc: HVDC, other: Other}
relevance_levels: {high: High, irrelevant: None}
priority_levels: {high: High, none: None}
routing: {auto_process_min_confidence: 0.6, llm_verify_min_confidence: 0.7}
""",
        encoding="utf-8",
    )
    with pytest.raises(CompanyPolicyLoadError, match="auto_process threshold"):
        load_company_policy(policy_file)


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.95, RoutingTarget.AUTO_PROCESS),
        (0.80, RoutingTarget.LLM_VERIFY),
        (0.69, RoutingTarget.HUMAN_REVIEW),
    ],
)
def test_confidence_routing(confidence: float, expected: RoutingTarget) -> None:
    evaluation = DecisionService(FixedEngine(confidence), _policy()).evaluate(_notice())
    assert evaluation.routing.target is expected
    assert evaluation.routing.overall_confidence == confidence


def test_input_hash_is_stable_and_policy_scoped() -> None:
    notice = _notice()
    assert decision_input_hash(notice, "v1") == decision_input_hash(notice, "v1")
    assert decision_input_hash(notice, "v1") != decision_input_hash(notice, "v2")


class FakeSystemOneClient:
    def __init__(self) -> None:
        self.request = None
        self.closed = False

    def system_one(self, state, questions, *, model):
        self.request = {"state": state, "questions": questions, "model": model}
        return SimpleNamespace(
            model="jev-1.13.0",
            choices={
                "product_family": SimpleNamespace(
                    choice="hil", confidence=0.96, probabilities={"hil": 0.96, "other": 0.04}
                ),
                "application": SimpleNamespace(
                    choice="hvdc", confidence=0.92, probabilities={"hvdc": 0.92, "other": 0.08}
                ),
                "company_relevance": SimpleNamespace(
                    choice="high",
                    confidence=0.94,
                    probabilities={"high": 0.94, "irrelevant": 0.06},
                ),
                "bid_priority": SimpleNamespace(
                    choice="high", confidence=0.91, probabilities={"high": 0.91, "none": 0.09}
                ),
            },
        )

    def close(self) -> None:
        self.closed = True


def test_jev_adapter_builds_one_typed_request_and_preserves_confidence() -> None:
    client = FakeSystemOneClient()
    decision = JevEngine(client=client, model="jev-test").decide(_notice(), _policy())
    assert client.request["model"] == "jev-test"
    assert set(client.request["questions"]) == {
        "product_family",
        "application",
        "company_relevance",
        "bid_priority",
    }
    assert client.request["questions"]["product_family"]["type"] == "choice"
    assert decision.model_version == "jev-1.13.0"
    assert decision.product_family.value is ProductFamily.HIL
    assert decision.product_family.confidence == 0.96
    assert decision.product_family.probabilities["other"] == 0.04
    assert client.closed is False


def test_storage_is_idempotent_for_same_request() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine, tables=[bid_pipeline, notice_decisions])
    evaluation = DecisionService(FixedEngine(0.95), _policy()).evaluate(_notice())
    with engine.begin() as connection:
        connection.execute(bid_pipeline.insert().values(notice_no=evaluation.notice_no))
        first_id = save_evaluation(connection, evaluation)
        second_id = save_evaluation(connection, evaluation)
        count = connection.execute(select(func.count()).select_from(notice_decisions)).scalar_one()
        row = connection.execute(select(notice_decisions)).mappings().one()
    assert first_id == second_id
    assert count == 1
    assert row["route"] == "auto_process"
    assert float(row["overall_confidence"]) == 0.95
    assert row["probabilities"]["product_family"]["hil"] == 0.95


def test_decision_table_matches_day1_contract() -> None:
    assert set(notice_decisions.c).issuperset(
        {
            notice_decisions.c.product_family,
            notice_decisions.c.application,
            notice_decisions.c.company_relevance,
            notice_decisions.c.bid_priority,
            notice_decisions.c.route,
            notice_decisions.c.human_result,
        }
    )
