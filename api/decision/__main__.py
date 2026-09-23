"""Run one opt-in decision from a JSON file; no collector integration is enabled."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from api.config import settings
from api.db import get_engine
from api.decision.engines import JevEngine
from api.decision.models import NoticeDecisionInput
from api.decision.policy import load_company_policy
from api.decision.service import DecisionService
from api.decision.storage import save_evaluation


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate one notice with the decision layer")
    parser.add_argument("--company", required=True, help="company.yaml policy path")
    parser.add_argument("--notice", required=True, help="notice JSON path")
    parser.add_argument(
        "--model",
        default=os.getenv("TYPESAFE_DEFAULT_MODEL", settings.typesafe_default_model),
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="persist to PostgreSQL; bid_pipeline must already contain notice_no",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    policy = load_company_policy(args.company)
    notice = NoticeDecisionInput.model_validate_json(Path(args.notice).read_text(encoding="utf-8"))
    service = DecisionService(
        JevEngine(model=args.model, api_key=settings.typesafe_api_key or None),
        policy,
    )
    evaluation = service.evaluate(notice)
    if args.save:
        with get_engine().begin() as connection:
            decision_id = save_evaluation(connection, evaluation)
        print(f"decision_id={decision_id}")
    print(evaluation.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
