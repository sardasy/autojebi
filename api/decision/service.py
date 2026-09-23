"""Pure orchestration from validated input to engine decision and routing."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import Connection

from api.decision.engine import DecisionEngine, DecisionEngineResponseError
from api.decision.models import CompanyPolicy, DecisionEvaluation, NoticeDecisionInput
from api.decision.routing import route_by_confidence
from api.decision.storage import save_evaluation


def decision_input_hash(notice: NoticeDecisionInput, policy_version: str | dict) -> str:
    canonical = json.dumps(
        {"notice": notice.model_dump(mode="json"), "policy_version": policy_version},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DecisionService:
    def __init__(self, engine: DecisionEngine, policy: CompanyPolicy) -> None:
        self._engine = engine
        self._policy = policy

    def evaluate(self, notice: NoticeDecisionInput) -> DecisionEvaluation:
        decision = self._engine.decide(notice, self._policy)
        if decision.policy_version != self._policy.policy_version:
            raise DecisionEngineResponseError("engine returned a different policy version")
        return DecisionEvaluation(
            notice_no=notice.notice_no,
            input_hash=decision_input_hash(notice, self._policy.model_dump(mode="json")),
            decision=decision,
            routing=route_by_confidence(decision, self._policy.routing),
        )

    def evaluate_and_save(self, connection: Connection, notice: NoticeDecisionInput) -> str:
        return save_evaluation(connection, self.evaluate(notice))
