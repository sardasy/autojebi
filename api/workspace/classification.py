"""Opt-in JEV requests: immutable policy snapshots and durable duplicate protection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from api.config import settings
from api.decision.models import DecisionEvaluation, NoticeDecisionInput
from api.decision.policy import CompanyPolicyLoadError, load_company_policy
from api.decision.storage import save_evaluation
from api.workspace.errors import WorkspaceError, fail
from api.workspace.identity import audit_details
from api.workspace.models import JobRecord
from api.workspace.tables import jobs


class ClassificationState(BaseModel):
    visible: bool = False
    enabled: bool
    message: str
    request_hash: str | None = None
    policy_version: str | None = None
    model: str | None = None
    current_job_id: str | None = None
    history: list[JobRecord] = Field(default_factory=list)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def prepare(ws: dict) -> dict:
    if not settings.workspace_jev_enabled:
        fail("jev_disabled", "JEV 분류가 활성화되지 않았습니다.")
    if not settings.typesafe_api_key.strip():
        fail("jev_key_missing", "JEV API 키를 설정하세요.")
    try:
        policy = load_company_policy(settings.workspace_jev_policy_path)
    except CompanyPolicyLoadError:
        fail("jev_policy_invalid", "JEV 회사 정책 파일을 확인하세요.")
    sources = sorted(
        [doc for doc in ws["inputs"].get("documents", []) if doc.get("role") == "notice_source"],
        key=lambda doc: doc["id"],
    )
    if not sources or any(not doc.get("text", "").strip() for doc in sources):
        fail("jev_source_missing", "공고 원문의 본문을 추출·반영한 뒤 실행하세요.")
    body = "\n\n".join(doc["text"] for doc in sources)
    if len(body) > 100_000:
        fail("jev_source_too_large", "JEV 분류 원문은 100,000자 이하여야 합니다.")
    facts = ws["inputs"]["notice"]
    notice = NoticeDecisionInput(
        notice_no=ws["notice_no"], title=facts.get("title") or "",
        organization=facts.get("org_name") or "", body=body,
        source_fields={"close_date": facts.get("close_date")},
    )
    content = {"notice": notice.model_dump(mode="json"), "policy": policy.model_dump(mode="json")}
    request = {**content, "model": settings.typesafe_default_model, "adapter_version": 1}
    return {**request, "content_hash": digest(content), "request_hash": digest(request)}


def history(conn: Any, notice_no: str) -> list[dict]:
    return [dict(row) for row in conn.execute(select(jobs).where(
        jobs.c.notice_no == notice_no, jobs.c.kind == "jev",
    ).order_by(jobs.c.created_at.desc())).mappings()]


def view(conn: Any, ws: dict, source_current: bool) -> ClassificationState:
    records = history(conn, ws["notice_no"])
    try:
        params = prepare(ws)
        if not source_current:
            fail("source_changed", "원문·회사 정보를 동기화한 뒤 실행하세요.")
    except WorkspaceError as exc:
        return ClassificationState(visible=settings.workspace_jev_enabled, enabled=False,
                                   message=exc.detail["message"], history=records)
    current = next((row for row in records
                    if row["parameters"].get("request_hash") == params["request_hash"]), None)
    return ClassificationState(
        visible=True, enabled=True, message="공고 원문과 설정된 회사 정책을 JEV로 전송합니다.",
        request_hash=params["request_hash"], policy_version=params["policy"]["policy_version"],
        model=params["model"], current_job_id=current["id"] if current else None,
        history=records,
    )


def enqueue(conn: Any, ws: dict, body: Any, create: Callable[..., dict]) -> dict:
    if ws["version"] != body.input_version:
        fail("version_conflict", "최신 입력으로 다시 실행하세요.")
    params = prepare(ws)
    if body.classification_hash != params["request_hash"]:
        fail("jev_input_changed", "JEV 원문·정책·모델이 변경되었습니다. 화면을 새로고침하세요.")
    prior_key = conn.execute(select(jobs).where(
        jobs.c.notice_no == ws["notice_no"], jobs.c.idempotency_key == body.idempotency_key,
    )).mappings().first()
    if prior_key and (prior_key["kind"] != "jev" or
                      prior_key["parameters"].get("request_hash") != params["request_hash"] or
                      prior_key["input_version"] != body.input_version):
        fail("idempotency_conflict", "같은 요청 키에 다른 작업이 지정되었습니다.")
    records = history(conn, ws["notice_no"])
    for record in records:
        # Failure/uncertainty also consumes this exact request. Never silently retry it.
        if record["parameters"].get("request_hash") == params["request_hash"]:
            return record
    if sum(row["parameters"].get("content_hash") == params["content_hash"] for row in records) >= 2:
        fail("jev_call_limit", "동일 원문·정책의 JEV 호출 한도 2회를 사용했습니다.")
    return create(conn, ws, "jev", body.idempotency_key, {**params, **audit_details()})


def assert_request_current(ws: dict, job: dict) -> None:
    if prepare(ws)["request_hash"] != job["parameters"].get("request_hash"):
        fail("jev_input_changed", "JEV 실행 중 원문·정책·모델이 변경되었습니다.")


def persist_result(conn: Any, ws: dict, job: dict, result: dict) -> dict:
    assert_request_current(ws, job)
    evaluation = DecisionEvaluation.model_validate(result["evaluation"])
    if evaluation.notice_no != job["notice_no"]:
        fail("jev_result_invalid", "JEV 결과의 공고가 일치하지 않습니다.")
    return {**result, "decision_id": save_evaluation(conn, evaluation)}
