"""Idempotent storage for evaluated decisions."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from api.decision.models import DecisionEvaluation
from api.decision.tables import notice_decisions


def _record_values(evaluation: DecisionEvaluation) -> dict:
    decision = evaluation.decision
    return {
        "id": str(uuid4()),
        "notice_no": evaluation.notice_no,
        "engine_name": decision.engine_name,
        "model_version": decision.model_version,
        "policy_version": decision.policy_version,
        "input_hash": evaluation.input_hash,
        "product_family": decision.product_family.value.value,
        "product_family_confidence": decision.product_family.confidence,
        "application": decision.application.value.value,
        "application_confidence": decision.application.confidence,
        "company_relevance": decision.company_relevance.value.value,
        "company_relevance_confidence": decision.company_relevance.confidence,
        "bid_priority": decision.bid_priority.value.value,
        "bid_priority_confidence": decision.bid_priority.confidence,
        "overall_confidence": evaluation.routing.overall_confidence,
        "route": evaluation.routing.target.value,
        "probabilities": {
            "product_family": decision.product_family.probabilities,
            "application": decision.application.probabilities,
            "company_relevance": decision.company_relevance.probabilities,
            "bid_priority": decision.bid_priority.probabilities,
        },
        "decision_payload": decision.model_dump(mode="json"),
    }


def save_evaluation(connection: Connection, evaluation: DecisionEvaluation) -> str:
    """Store the first result for an identical request and return its stable id."""
    values = _record_values(evaluation)
    conflict_columns = [
        "notice_no",
        "input_hash",
        "engine_name",
        "model_version",
        "policy_version",
    ]
    if connection.dialect.name == "postgresql":
        statement = (
            postgresql_insert(notice_decisions)
            .values(**values)
            .on_conflict_do_nothing(index_elements=conflict_columns)
        )
    elif connection.dialect.name == "sqlite":
        statement = (
            sqlite_insert(notice_decisions)
            .values(**values)
            .on_conflict_do_nothing(index_elements=conflict_columns)
        )
    else:
        statement = notice_decisions.insert().values(**values)
    connection.execute(statement)
    existing_id = connection.execute(
        select(notice_decisions.c.id).where(
            notice_decisions.c.notice_no == evaluation.notice_no,
            notice_decisions.c.input_hash == evaluation.input_hash,
            notice_decisions.c.engine_name == evaluation.decision.engine_name,
            notice_decisions.c.model_version == evaluation.decision.model_version,
            notice_decisions.c.policy_version == evaluation.decision.policy_version,
        )
    ).scalar_one()
    return str(existing_id)
