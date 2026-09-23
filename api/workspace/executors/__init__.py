"""Job executors, one module per job kind (ADR 0001). ``execute`` dispatches a claimed job."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api.workspace.errors import fail

# Import submodules (not same-named functions) so `executors.<kind>` stays the module.
from api.workspace.executors import analyze, excel, extract, fetch, hwp, package
from api.workspace.hwp_inspection import inspect_template
from api.workspace.proposal import generate_proposal
from api.workspace.readiness import readiness_issues
from api.workspace.readiness_issues import render_blockers
from api.workspace.storage import storage_root


def execute(engine: Any, job: dict) -> dict:
    if job["kind"] == "spec_index":
        # Lazy: needs the optional `spec-search` extra.
        from api.specifications.indexing import build

        return build(engine, job)
    folder = storage_root() / "exports" / job["id"]
    folder.mkdir(parents=True, exist_ok=True)
    if job["kind"] == "analyze":
        return analyze.analyze(engine, job)
    if job["kind"] == "extract":
        return extract.extract(job)
    if job["kind"] == "fetch":
        return fetch.fetch_sources(job)
    if job["kind"] == "excel":
        return excel.run_excel(job, folder)
    if job["kind"] == "hwp":
        return hwp.run_hwp(engine, job, folder)
    if job["kind"] == "hwp_inspect":
        with engine.begin() as conn:
            preview = hwp.hwp_preview(conn, job["snapshot"], job["parameters"]["template_key"])
        return inspect_template(preview["template"], preview["mappings"],
                                visible=job["parameters"].get("visible", False), operation_id=job["id"])
    if job["kind"] == "package":
        return package.run_package(engine, job, folder)
    if job["kind"] == "notify":
        return {
            "delivered": False,
            "dry_run": True,
            "warnings": [],
            "preview": job["snapshot"]["notice"],
        }
    reqs = job["snapshot"]["requirements"]
    if not reqs:
        fail("requirements_missing", "원본 근거가 있는 요구사항을 먼저 등록하세요.")
    if job["kind"] == "grade":
        # Lazy: loads the Qdrant/fastembed stack only for grading jobs.
        from api.workspace.grading import grade

        return grade(engine, job)
    if job["kind"] == "proposal":
        return generate_proposal(engine, job)
    reasons = readiness_issues(job["snapshot"])
    return {
        "warnings": render_blockers(reasons),
        "readiness_issues": [item.model_dump(mode="json") for item in reasons],
        "readiness_input_version": job["input_version"],
        "readiness_checked_at": datetime.now(UTC).isoformat(),
        "verified": False,
        "message": "자동 검사는 사람의 사실 확인을 대체하지 않습니다.",
    }
