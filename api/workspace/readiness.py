"""Readiness predicates shared by workspace, verification and generated packages."""

from datetime import UTC, datetime

from api.specifications import service as specifications
from api.workspace import asset_policy, output_plan, source_needs, writing_plan
from api.workspace.errors import HANDLED_ERRORS
from api.workspace.forms import filling
from api.workspace.provenance import (
    commercial_valid,
    proposal_coverage,
    requirement_valid,
    section_valid,
)
from api.workspace.readiness_issues import IssueCode, ReadinessIssue, issue
from api.workspace.source_inventory import source_readiness_issues, source_text_complete
from api.workspace.storage import source_path


def deadline_readiness_issues(inputs: dict, *, at: datetime | None = None) -> list[ReadinessIssue]:
    value = (inputs.get("notice") or {}).get("close_date")
    try:
        deadline = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return [issue(IssueCode.DEADLINE_UNKNOWN, "notice")]
    if deadline.tzinfo is None:
        return [issue(IssueCode.DEADLINE_TIMEZONE_UNKNOWN, "notice")]
    if deadline <= (at or datetime.now(UTC)):
        return [issue(IssueCode.DEADLINE_PASSED, "notice")]
    return []


def file_readiness_issues(inputs: dict) -> list[ReadinessIssue]:
    issues = []
    for doc in inputs.get("documents") or []:
        try:
            source_path(doc)
            if not doc.get("sha256"):
                issues.append(issue(IssueCode.SOURCE_CHECKSUM_MISSING, "document", doc["id"], name=doc.get("name", doc["id"])))
        except HANDLED_ERRORS:
            issues.append(issue(IssueCode.SOURCE_FILE_INVALID, "document", doc["id"], name=doc.get("name", doc["id"])))
    return issues


def readiness_issues(inputs: dict) -> list[ReadinessIssue]:
    issues = source_readiness_issues(inputs)
    issues.extend(source_needs.readiness_issues(inputs))
    issues.extend(filling.filling_readiness_issues(inputs))
    issues.extend(output_plan.writing_output_readiness_issues(inputs))
    if inputs.get("specifications") or specifications.enabled():
        if specifications.summary(inputs)["spec_compliance"] != "충족":
            issues.append(issue(IssueCode.SPEC_REVIEW_REQUIRED, "workspace"))
    if inputs.get("writing_plan"):
        if not writing_plan.current(inputs):
            issues.append(issue(IssueCode.WRITING_PLAN_STALE, "workspace"))
        written = {s["id"] for s in inputs.get("proposal_sections", []) if s.get("text", "").strip()}
        issues.extend(issue(IssueCode.WRITING_TARGET_EMPTY, "writing_target", item["id"], title=item["title"]) for item in inputs["writing_plan"]["items"]
                      if item["action"] == "write" and item["id"] not in written)
    if not inputs.get("source_reviewed"):
        issues.append(issue(IssueCode.SOURCE_REVIEW_REQUIRED, "notice"))
    docs = inputs.get("documents") or []
    for doc in docs:
        code = asset_policy.document_issue_code(doc, inputs.get("company") or {})
        if code:
            issues.append(issue(code, "document", doc["id"], name=doc.get("name", doc["id"])))
    if not source_text_complete(inputs):
        issues.append(issue(IssueCode.SOURCE_EXTRACTION_REQUIRED, "notice"))
    for item in inputs.get("checklist") or []:
        if not any(
            d.get("confirmed")
            and not asset_policy.document_issue(d, inputs.get("company") or {})
            and d.get("role") in {"company_evidence", "product_evidence"}
            and str(d.get("text") or "").strip()
            and d.get("item_id") == item["id"]
            for d in docs
        ):
            issues.append(issue(IssueCode.EVIDENCE_UNCONFIRMED, "checklist", item["id"], name=item["name"]))
    reqs = inputs.get("requirements") or []
    if not reqs:
        issues.append(issue(IssueCode.REQUIREMENTS_MISSING, "notice"))
    documents = {d["id"]: d for d in docs}
    for req in reqs:
        if req.get("mandatory") and not requirement_valid(req, documents):
            issues.append(issue(IssueCode.REQUIREMENT_REVIEW_REQUIRED, "requirement", req["id"], text=req["text"][:80]))
        if req.get("mandatory", True) and req.get("compliance", "unassessed") != "meets":
            issues.append(issue(IssueCode.REQUIREMENT_COMPLIANCE_REQUIRED, "requirement", req["id"], text=req["text"][:80]))
    if inputs.get("commercial") is not None and not commercial_valid(inputs["commercial"], documents):
        issues.append(issue(IssueCode.COMMERCIAL_REVIEW_REQUIRED, "commercial"))
    sections = inputs.get("proposal_sections") or []
    if (not sections and not output_plan.attachment_only(inputs)) or any(
        s.get("review_status") != "approved" or not section_valid(s, inputs) for s in sections
    ):
        issues.append(issue(IssueCode.PROPOSAL_REVIEW_REQUIRED, "proposal"))
    missing = set() if output_plan.attachment_only(inputs) else set(proposal_coverage(inputs)["missing_ids"])
    for req in reqs:
        if req["id"] in missing:
            issues.append(issue(IssueCode.PROPOSAL_COVERAGE_MISSING, "requirement", req["id"], text=req["text"][:80]))
    return issues

