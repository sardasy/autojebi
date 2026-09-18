"""Apply a finished job's result to the versioned workspace inputs (moved from the router, R2)."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select

from api.workspace import service
from api.workspace.tables import jobs


def apply_job_result(conn: Any, notice_no: str, job_id: str, version: int) -> None:
    """Merge a succeeded job's result into the current inputs as a new, review-pending version.

    No-op when the result adds nothing. Raises ``WorkspaceError`` for stale or conflicting results.
    """
    ws = service.load(conn, notice_no, version)
    service.assert_source_current(conn, ws)
    job = (
        conn.execute(select(jobs).where(jobs.c.id == job_id, jobs.c.notice_no == notice_no))
        .mappings()
        .first()
    )
    if not job or job["status"] != "succeeded" or job["input_version"] != ws["version"]:
        service.fail("stale_result", "현재 버전에서 완료된 결과만 반영할 수 있습니다.")
    inputs = copy.deepcopy(ws["inputs"])
    if job["kind"] == "fetch":
        existing = {d["id"]: d for d in inputs["documents"]}
        for document in job["result"]["documents"]:
            target = existing.get(document["id"])
            if target is None:
                target = copy.deepcopy(document)
                inputs["documents"].append(target)
                existing[target["id"]] = target
            elif "attachment_index" in document and "attachment_url" in document:
                if target.get("role") != "notice_source" or document.get("role") != "notice_source":
                    service.fail("source_identity_conflict", "회사·제품 증빙을 공고 첨부로 덮어쓸 수 없습니다.")
                target.update(
                    attachment_index=document["attachment_index"],
                    attachment_url=document["attachment_url"],
                )
    elif job["kind"] == "extract":
        for doc in inputs["documents"]:
            found = next((d for d in job["result"]["documents"] if d["id"] == doc["id"]), None)
            if found:
                if doc.get("text") != found["text"]:
                    doc["confirmed"] = False
                doc.update(text=found["text"], text_origin=found["format"])
                if "extraction" in found:
                    doc["extraction"] = copy.deepcopy(found["extraction"])
                    if not found["extraction"].get("complete", False):
                        doc["confirmed"] = False
                        inputs["source_reviewed"] = False
    elif job["kind"] == "proposal":
        written = [s for s in inputs.get("proposal_sections") or [] if s.get("document_kind")]
        generated = job["result"]["sections"]
        if {s["id"] for s in written} & {s["id"] for s in generated}:
            service.fail("draft_conflict", "작성한 서류와 생성 결과의 식별자가 겹칩니다.")
        inputs["proposal_sections"] = written + generated
    elif job["kind"] == "analyze":

        def identity(requirement: dict) -> tuple:
            return tuple(
                requirement.get(key) for key in ("document_id", "quote", "category", "text")
            )

        seen = {identity(r) for r in inputs["requirements"]}
        additions = []
        for requirement in job["result"]["requirements"]:
            key = identity(requirement)
            if key not in seen:
                additions.append(
                    {**requirement, "id": service.uid(), "review_status": "pending",
                     "compliance": "unassessed"}
                )
                seen.add(key)
        if not additions:
            return
        inputs["requirements"].extend(additions)
    else:
        service.fail("not_applicable", "반영 대상 작업이 아닙니다.")
    if job["kind"] != "extract":
        inputs["source_reviewed"] = False
    if inputs == ws["inputs"]:
        return
    changed = service.change(
        conn,
        ws,
        inputs,
        "extract_result" if job["kind"] == "extract" else "apply_result",
        "사용자가 작업 결과를 검토 대상으로 반영",
    )
    if job["kind"] == "analyze":
        # Lazy: api.specifications.service imports api.workspace.service (cycle).
        from api.specifications.service import sync_adopted

        sync_adopted(conn, changed)
