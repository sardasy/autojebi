"""One explicit JEV request per reserved workspace job; never approves inputs."""

from typing import Any

from api.config import settings
from api.decision.engines import JevEngine
from api.decision.models import CompanyPolicy, NoticeDecisionInput
from api.decision.service import DecisionService
from api.workspace.classification import assert_request_current
from api.workspace.errors import fail
from api.workspace.service import load


def classify(engine: Any, job: dict) -> dict:
    with engine.begin() as conn:
        ws = load(conn, job["notice_no"], job["input_version"])
        assert_request_current(ws, job)
    params = job["parameters"]
    policy = CompanyPolicy.model_validate(params["policy"])
    notice = NoticeDecisionInput.model_validate(params["notice"])
    try:
        evaluation = DecisionService(JevEngine(
            model=params["model"], api_key=settings.typesafe_api_key,
        ), policy).evaluate(notice)
    except Exception:
        # SDK exceptions may include credentials or source text; never expose them.
        fail("jev_unavailable", "JEV 분류 미평가: 연결 또는 응답을 확인할 수 없습니다.",
             "인증·서비스 상태를 확인하세요. 동일 요청은 자동 재시도하지 않습니다.", status=502)
    return {"evaluation": evaluation.model_dump(mode="json"), "warnings": []}
