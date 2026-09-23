from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update

from api.db.tables import (
    bid_pipeline,
    company_profiles,
    document_field_mappings,
    hwp_templates,
)
from api.services.notice_facts import normalize_notice_facts
from api.workspace import (
    asset_policy,
    classification,
    document_jobs,
    identity,
    notice_brief,
    output_plan,
    readiness,
    writing_plan,
)
from api.workspace.errors import fail
from api.workspace.models import JobRecord, WorkspaceRecord
from api.workspace.provenance import (
    invalidate_document_dependents,
    proposal_coverage,
)
from api.workspace.readiness_issues import IssueCode, issue, render_blockers
from api.workspace.source_inventory import (
    source_inventory,
    source_inventory_issues,
)
from api.workspace.tables import jobs, reviews, workspaces


def now() -> datetime:
    return datetime.now(UTC)


def uid() -> str:
    return str(uuid.uuid4())


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def notice_facts(source: dict) -> dict:
    normalized = normalize_notice_facts(source.get("raw"))
    for key in (
        "notice_no", "title", "org_name", "org_code",
        "close_date",
        "open_date",
        "base_price",
        "source",
        "bid_no",
        "bid_seq",
    ):
        value = source.get(key)
        if value is not None and value != "":
            normalized[key] = value
        else:
            normalized.setdefault(key, None)
    if normalized.get("base_price") is not None:
        normalized["base_price"] = normalize_notice_facts(
            {"base_price": normalized["base_price"]}
        ).get("base_price")
    return json.loads(json.dumps(normalized, default=str))


def source_data(conn: Any, notice_no: str) -> tuple[dict, str]:
    row = (
        conn.execute(select(bid_pipeline).where(bid_pipeline.c.notice_no == notice_no))
        .mappings()
        .first()
    )
    if not row:
        fail("not_found", "공고를 찾을 수 없습니다.", status=404)
    data = dict(row)
    profile = (
        conn.execute(
            select(company_profiles)
            .where(company_profiles.c.active.is_(True))
            .order_by(company_profiles.c.id)
        )
        .mappings()
        .first()
    )
    data["company"] = dict(profile) if profile else {}
    docs = (data.get("analysis") or {}).get("document_automation") or {}
    signature = {"notice": notice_facts(data), "raw": data.get("raw"), "company": data["company"]}
    signature["uploads"] = docs.get("uploads") or []
    signature["checklist"] = docs.get("checklist") or []
    signature["templates"] = [
        dict(r) for r in conn.execute(select(hwp_templates).order_by(hwp_templates.c.id)).mappings()
    ]
    signature["mappings"] = [
        dict(r)
        for r in conn.execute(
            select(document_field_mappings).order_by(document_field_mappings.c.id)
        ).mappings()
    ]
    root = Path(os.getenv("HWP_TEMPLATE_ROOT", "data")).resolve()
    signature["template_files"] = []
    for template in signature["templates"]:
        path = Path(template["template_path"])
        path = (path if path.is_absolute() else root / path).resolve()
        checksum = (
            hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_relative_to(root) and path.is_file()
            else None
        )
        signature["template_files"].append((template["id"], checksum))
    return data, digest(signature)


def load(conn: Any, notice_no: str, version: int | None = None) -> dict:
    row = (
        conn.execute(
            select(workspaces).where(workspaces.c.notice_no == notice_no).with_for_update()
        )
        .mappings()
        .first()
    )
    if not row:
        fail("not_initialized", "검토 작업대를 먼저 시작하세요.", status=404)
    if version is not None and row["version"] != version:
        fail("version_conflict", "다른 변경사항이 있습니다. 최신 화면을 불러오세요.")
    return dict(row)


def assert_source_current(conn: Any, workspace: dict) -> None:
    _, signature = source_data(conn, workspace["notice_no"])
    if signature != workspace["source_hash"]:
        fail(
            "source_changed",
            "원문 또는 회사 정보가 변경되었습니다.",
            "원문 동기화 후 다시 검토하세요.",
        )


def audit(
    conn: Any, ws: dict, action: str, note: str, details: dict, job_id: str | None = None
) -> None:

    if not note.strip():
        fail("note_required", "검토 의견을 입력하세요.", status=422)
    conn.execute(
        reviews.insert().values(
            id=uid(),
            notice_no=ws["notice_no"],
            input_version=ws["version"],
            job_id=job_id,
            action=action,
            note=note.strip(),
            details=identity.audit_details(notice_brief.audit_snapshot(action, ws["inputs"], details)),
            created_at=now(),
        )
    )


def change(conn: Any, ws: dict, inputs: dict, action: str, note: str, **extra: Any) -> dict:
    inputs = copy.deepcopy(inputs)
    if not note.strip():
        fail("note_required", "검토 의견을 입력하세요.", status=422)
    if action == "decision" and extra.get("decision") == ws["decision"] and inputs == ws["inputs"]:
        return ws
    invalidate_document_dependents(ws["inputs"], inputs)
    if action not in {"decision", "source_review", "section_review", "notice_form_review", "extract_result", "reference_upload", "reference_text", "reference_draft", "output_plan", "source_display_review"}:
        for section in inputs.get("proposal_sections") or []:
            if section.get("review_status") != "rejected":
                section["review_status"] = "pending"
    if inputs.get("form_fillings"):
        from api.workspace.forms.filling import review_basis
        basis = review_basis(inputs)
        for filling in inputs["form_fillings"]:
            if (filling.get("review_status") == "approved"
                    and (filling.get("review") or {}).get("basis_sha256") != basis):
                filling["review_status"] = "pending"
    updated = {"inputs": inputs, "version": ws["version"] + 1, "updated_at": now(), **extra}
    count = conn.execute(
        update(workspaces)
        .where(workspaces.c.notice_no == ws["notice_no"], workspaces.c.version == ws["version"])
        .values(**updated)
    ).rowcount
    if count != 1:
        fail("version_conflict", "입력이 변경되었습니다. 다시 확인하세요.")
    result = {**ws, **updated}
    audit(
        conn,
        result,
        action,
        note,
        {
            "previous_version": ws["version"],
            "previous_inputs": ws["inputs"],
            "previous_decision": ws["decision"],
        },
    )
    return result


def initialize(conn: Any, notice_no: str, version: int | None = None) -> dict:
    existing = (
        conn.execute(select(workspaces).where(workspaces.c.notice_no == notice_no))
        .mappings()
        .first()
    )
    if existing and version is None:
        return dict(existing)
    source, signature = source_data(conn, notice_no)
    automation = (source.get("analysis") or {}).get("document_automation") or {}
    documents = []
    for doc in automation.get("uploads") or []:
        documents.append(
            {
                **doc,
                "role": "notice_source"
                if doc.get("source_ref") == "g2b_attachment"
                else "company_evidence",
                "confirmed": False,
                "text": doc.get("text_excerpt") if not doc.get("text_extract_error") else "",
                "text_origin": "legacy_excerpt",
            }
        )
    facts = notice_facts(source)
    checklist = [
        {**item, "status": "needed", "confirmed": False}
        for item in automation.get("checklist") or []
        if item.get("required")
    ]
    inputs = {
        "notice": facts,
        "raw": source.get("raw") or {},
        "documents": documents,
        "requirements": [],
        "checklist": checklist,
        "company": json.loads(json.dumps(source["company"], default=str)),
        "source_reviewed": False,
        "legacy_warning": bool((source.get("analysis") or {}).get("error"))
        or source["status"] == "archived_low",
    }
    if existing:
        ws = load(conn, notice_no, version)
        inputs["documents"] += [
            d for d in ws["inputs"]["documents"] if d["id"] not in {x["id"] for x in documents}
        ]
        # Preserve manual work, but require reconfirmation against the changed source.
        inputs["requirements"] = [
            {
                **r,
                "review_status": "rejected" if r.get("review_status") == "rejected" else "pending",
                "compliance": "unassessed",
            }
            for r in ws["inputs"]["requirements"]
        ]
        inputs["proposal_sections"] = copy.deepcopy(ws["inputs"].get("proposal_sections") or [])
        if "output_plan" in ws["inputs"]:
            inputs["output_plan"] = copy.deepcopy(ws["inputs"]["output_plan"])
        if "form_fillings" in ws["inputs"]:
            inputs["form_fillings"] = copy.deepcopy(ws["inputs"]["form_fillings"])
        if "commercial" in ws["inputs"]:
            inputs["commercial"] = copy.deepcopy(ws["inputs"]["commercial"])
        return change(
            conn,
            ws,
            inputs,
            "source_sync",
            "원본/회사 정보 동기화; 이전 승인은 과거 버전에 보존",
            source_hash=signature,
        )
    values = dict(
        notice_no=notice_no,
        version=1,
        decision="pending",
        inputs=inputs,
        source_hash=signature,
        created_at=now(),
        updated_at=now(),
    )
    conn.execute(workspaces.insert().values(**values))
    audit(conn, values, "initialized", "기존 원본 보존, 과거 승인과 AI 점수는 승계하지 않음", {})
    return values


def deadline_issues(inputs: dict) -> list[str]:
    return render_blockers(readiness.deadline_readiness_issues(inputs, at=now()))


def blockers(inputs: dict) -> list[str]:
    return render_blockers(readiness.readiness_issues(inputs))


def input_file_issues(inputs: dict) -> list[str]:
    return render_blockers(readiness.file_readiness_issues(inputs))



def view(conn: Any, notice_no: str) -> WorkspaceRecord:
    ws = load(conn, notice_no)
    _, signature = source_data(conn, notice_no)
    records = (
        conn.execute(
            select(jobs).where(jobs.c.notice_no == notice_no).order_by(jobs.c.created_at.desc(), jobs.c.id.desc())
        )
        .mappings()
        .all()
    )
    history = (
        conn.execute(
            select(reviews)
            .where(reviews.c.notice_no == notice_no)
            .order_by(reviews.c.created_at.desc(), reviews.c.id.desc())
        )
        .mappings()
        .all()
    )
    checked_at = now()
    reasons = readiness.deadline_readiness_issues(ws["inputs"], at=checked_at) + readiness.readiness_issues(ws["inputs"])
    if ws["source_hash"] != signature:
        reasons.insert(0, issue(IssueCode.SOURCE_CHANGED, "workspace"))
    if not reasons:
        reasons.extend(readiness.file_readiness_issues(ws["inputs"]))
    issues = render_blockers(reasons)
    latest_reviews = {}
    for item in history:
        if item["input_version"] == ws["version"] and item["job_id"]:
            latest_reviews.setdefault(item["job_id"], item["action"])
    ready = False
    if not issues and ws["decision"] == "participate":
        for job in records:
            result = job["result"] or {}
            if (
                latest_reviews.get(job["id"]) == "ready"
                and job["kind"] == "package"
                and job["status"] == "succeeded"
            ):
                ready = not result.get("warnings") and package_current(conn, ws, job)
                if ready:
                    break
    public_inputs = copy.deepcopy(ws["inputs"])
    for requirement in public_inputs.get("requirements") or []:
        requirement.setdefault("compliance", "unassessed")
    for doc in public_inputs["documents"]:
        doc.pop("storage_path", None)
        if doc.get("company_asset"):
            doc["asset_issue"] = asset_policy.document_issue(doc, public_inputs.get("company") or {})
            if doc["asset_issue"]:
                doc["confirmed"] = False
    from api.workspace.source_needs import inventory as needs_inventory
    return WorkspaceRecord(
        notice_brief=notice_brief.public_brief(ws["inputs"], history),
        **_spec_summary(ws["inputs"]),
        writing_plan_current=writing_plan.current(ws["inputs"]),
        notice_no=notice_no,
        version=ws["version"],
        decision=ws["decision"],
        inputs=public_inputs,
        blockers=issues,
        readiness_issues=reasons,
        readiness_checked_at=checked_at,
        next_action=issues[0] if issues else "제출 준비 확인 완료 · 최종 패키지를 다운로드하세요" if ready else "생성물 검토 및 제출 준비 확인",
        jobs=[JobRecord(**r) for r in records],
        reviews=notice_brief.public_reviews(history),
        source_changed=ws["source_hash"] != signature,
        ready=ready,
        proposal_coverage=proposal_coverage(ws["inputs"]),
        source_attachments=source_inventory(ws["inputs"]),
        source_needs=needs_inventory(ws["inputs"]),
    )


def artifact_healthy(job: dict) -> bool:
    result = job.get("result") or {}
    if not result.get("artifact") or not result.get("sha256"):
        return False
    try:
        path = Path(result["artifact"])
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == result["sha256"]
    except OSError:
        return False


def _spec_summary(inputs: dict) -> dict:
    from api.specifications.service import summary
    value = summary(inputs)
    return {"spec_compliance": value["spec_compliance"],
            "unresolved_spec_count": value["unresolved_spec_count"],
            "spec_source_complete": value["source_complete"]}


def latest_review(conn: Any, job_id: str) -> dict | None:
    row = (
        conn.execute(
            select(reviews)
            .where(reviews.c.job_id == job_id)
            .order_by(reviews.c.created_at.desc(), reviews.c.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def package_current(conn: Any, ws: dict, package: dict) -> bool:

    if not artifact_healthy(package):
        return False
    records = list(conn.execute(select(jobs).where(
        jobs.c.notice_no == ws["notice_no"], jobs.c.input_version == ws["version"],
        jobs.c.kind.in_(["excel", "hwp"])
    ).order_by(jobs.c.created_at.desc(), jobs.c.id.desc())).mappings())
    keys = set(output_plan.template_keys(ws["inputs"]))
    if any(j["status"] in {"queued", "running"} and
           (j["kind"] == "excel" or j["parameters"].get("template_key") in keys) for j in records):
        return False
    selected = output_plan.selected_artifacts(records, ws["inputs"])
    included = (package.get("result") or {}).get("included_jobs") or []
    if not included or set(included) != {j["id"] for j in selected}:
        return False
    if not any(j["kind"] == "excel" for j in selected) or keys != {
        j["parameters"].get("template_key") for j in selected if j["kind"] == "hwp"
    }:
        return False
    return all(artifact_healthy(j) and output_plan.review_matches(j, latest_review(conn, j["id"]))
               for j in selected)


def create_job_record(conn: Any, ws: dict, kind: str, key: str, params: dict) -> dict:
    record = dict(
        id=uid(), notice_no=ws["notice_no"], kind=kind,
        input_version=ws["version"], idempotency_key=key, status="queued",
        snapshot=ws["inputs"], parameters=params, created_at=now(),
    )
    conn.execute(jobs.insert().values(**record))
    return record


def enqueue(conn: Any, notice_no: str, body: Any) -> dict:
    params = document_jobs.parameters(conn, notice_no, body)
    if body.kind == "spec_index":
        from api.specifications.service import require_enabled
        require_enabled()
    ws = load(conn, notice_no)
    if body.kind == "jev":
        assert_source_current(conn, ws)
        return classification.enqueue(conn, ws, body, create_job_record)
    previous = (
        conn.execute(
            select(jobs).where(
                jobs.c.notice_no == notice_no, jobs.c.idempotency_key == body.idempotency_key
            )
        )
        .mappings()
        .first()
    )
    if previous:
        if (
            previous["kind"] != body.kind
            or previous["input_version"] != body.input_version
            or previous["parameters"] != params
        ):
            fail("idempotency_conflict", "같은 요청 키에 다른 작업이 지정되었습니다.")
        return dict(previous)
    if ws["version"] != body.input_version:
        fail("version_conflict", "최신 입력으로 다시 실행하세요.")
    assert_source_current(conn, ws)
    previous = (
        conn.execute(
            select(jobs)
            .where(
                jobs.c.notice_no == notice_no,
                jobs.c.input_version == ws["version"],
                jobs.c.kind == body.kind,
                jobs.c.status.in_(["queued", "running", "succeeded"]),
            )
            .order_by(jobs.c.created_at.desc())
        )
        .mappings()
        .all()
    )
    for job in previous:
        if not document_jobs.reusable(body.kind, job["parameters"], params):
            continue
        if body.kind == "spec_index" and job["status"] == "succeeded":
            continue
        if body.kind == "fetch" and job["status"] == "succeeded" and source_inventory_issues(ws["inputs"]):
            pending = {
                **ws["inputs"],
                "documents": [*ws["inputs"]["documents"], *((job["result"] or {}).get("documents") or [])],
            }
            if any(not item["document_ids"] for item in source_inventory(pending)):
                continue
        if job["parameters"].get("template_key") == body.template_key and not (
            body.kind == "package" and job["status"] == "succeeded"
        ):
            if job["status"] == "succeeded" and job["kind"] in {"excel", "hwp"}:
                reviewed = latest_review(conn, job["id"])
                if not artifact_healthy(job) or (reviewed and reviewed["action"] == "rejected"):
                    fail(
                        "artifact_recovery_required",
                        "기존 생성물의 파일 또는 검토 상태를 확인하세요.",
                        "해당 실행 기록에서 복구·재생성을 요청하세요.",
                    )
            return dict(job)
    if body.kind in {"hwp", "hwp_inspect"}:
        for old in conn.execute(
            select(jobs).where(jobs.c.notice_no == notice_no, jobs.c.kind.in_(["hwp", "hwp_inspect"]))
        ).mappings():
            if old["parameters"].get("attempt_only"):
                continue
            if old["status"] == "running":
                fail(
                    "hwp_running",
                    "다른 HWP 작업이 실행 중입니다.",
                    "실행 결과를 확인한 뒤 다시 요청하세요.",
                )
            uncertain = old["status"] == "failed" or (
                old["status"] == "blocked"
                and (old["error"] or {}).get("code")
                in {"version_conflict", "source_changed", "worker_output_path"}
            )
            if uncertain:
                acknowledged = conn.execute(
                    select(reviews.c.id).where(
                        reviews.c.job_id == old["id"], reviews.c.action == "recovery_requested"
                    )
                ).first()
                if not acknowledged:
                    fail(
                        "hwp_recovery_required",
                        "이전 HWP 실행 결과가 불확실합니다.",
                        "Worker와 기존 파일 확인 후 해당 기록에서 복구를 요청하세요.",
                    )
    return create_job_record(conn, ws, body.kind, body.idempotency_key, params)


def recover_job(conn: Any, job_id: str, body: Any) -> dict:
    original = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
    if not original:
        fail("job_not_found", "복구할 실행 기록이 없습니다.", status=404)
    if original["kind"] == "jev":
        fail("jev_recovery_blocked", "JEV 실패 기록은 보존됩니다. 동일 요청은 재실행하지 않습니다.")
    ws = load(conn, original["notice_no"], body.version)
    prior = (
        conn.execute(
            select(jobs).where(
                jobs.c.notice_no == ws["notice_no"], jobs.c.idempotency_key == body.idempotency_key
            )
        )
        .mappings()
        .first()
    )
    params = {
        "template_key": original["parameters"].get("template_key", "bid_form"),
        "recovery_of": job_id,
        "recovery_note": body.note.strip(),
        "external_state_confirmed": body.external_state_confirmed,
        "visible": body.visible,
    }
    if prior:
        if prior["input_version"] != body.version or prior["parameters"] != params:
            fail("idempotency_conflict", "같은 복구 요청 키의 내용이 다릅니다.")
        return dict(prior)
    assert_source_current(conn, ws)
    if not body.note.strip():
        fail("note_required", "복구 사유를 입력하세요.", status=422)
    replacements = conn.execute(
        select(jobs)
        .where(jobs.c.notice_no == ws["notice_no"], jobs.c.input_version == ws["version"])
        .order_by(jobs.c.created_at.desc())
    ).mappings()
    for replacement in replacements:
        if replacement["parameters"] == params:
            if replacement["status"] in {"queued", "running"} or (
                replacement["status"] == "succeeded" and artifact_healthy(replacement)
            ):
                return dict(replacement)
            fail(
                "replacement_needs_review",
                "복구 작업에도 확인할 문제가 있습니다.",
                "최신 복구 실행 기록에서 다시 확인하세요.",
            )
    if original["status"] in {"queued", "running"}:
        fail("job_active", "실행 중이거나 대기 중인 작업은 재실행할 수 없습니다.")
    review = latest_review(conn, job_id)
    if (
        original["status"] == "succeeded"
        and artifact_healthy(original)
        and not (review and review["action"] == "rejected")
    ):
        fail("recovery_unnecessary", "정상 생성물은 기존 파일을 사용하세요.")
    if original["status"] == "succeeded" and original["kind"] not in {"excel", "hwp", "package"}:
        fail("recovery_unnecessary", "정상 실행 결과를 사용하세요.")
    active = (
        conn.execute(
            select(jobs).where(
                jobs.c.notice_no == ws["notice_no"],
                jobs.c.kind == original["kind"],
                jobs.c.status.in_(["queued", "running"]),
            )
        )
        .mappings()
        .all()
    )
    for item in active:
        if original["kind"] in {"hwp", "hwp_inspect"} or item["input_version"] == ws["version"]:
            fail("job_active", "같은 종류의 실행이 이미 접수되어 있습니다.")
    if original["kind"] in {"hwp", "hwp_inspect"} and not body.external_state_confirmed:
        fail(
            "hwp_confirmation_required",
            "Worker 종료와 기존 생성 파일 확인이 필요합니다.",
            "확인 후 복구 요청의 확인 항목을 선택하세요.",
        )
    record = create_job_record(conn, ws, original["kind"], body.idempotency_key, params)
    audit(
        conn,
        ws,
        "recovery_requested",
        body.note,
        {
            "replacement_job_id": record["id"],
            "external_state_confirmed": body.external_state_confirmed,
        },
        job_id,
    )
    return record


def review_artifact(conn: Any, notice_no: str, body: Any) -> None:
    ws = load(conn, notice_no, body.version)
    assert_source_current(conn, ws)
    job = (
        conn.execute(select(jobs).where(jobs.c.id == body.job_id, jobs.c.notice_no == notice_no))
        .mappings()
        .first()
    )
    if not job or job["input_version"] != ws["version"]:
        fail("stale_artifact", "현재 입력 버전의 생성물을 선택하세요.")
    previous = latest_review(conn, body.job_id)
    if (previous["id"] if previous else None) != body.expected_review_id:
        fail(
            "review_conflict",
            "다른 창에서 검토 상태가 변경되었습니다.",
            "최신 검토 결과를 불러온 뒤 다시 판단하세요.",
        )
    result = job["result"] or {}
    if body.action in {"approved", "ready"}:
        if job["status"] != "succeeded" or not result.get("artifact"):
            fail("not_generated", "실패하거나 파일이 없는 작업은 승인할 수 없습니다.")
        path = Path(result["artifact"])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != result.get(
            "sha256"
        ):
            fail("file_changed", "생성 파일이 없어졌거나 변경되었습니다.")
        if body.output_sha256 is not None and body.output_sha256 != result.get("sha256"):
            fail("file_changed", "화면에서 검토한 파일과 현재 파일이 다릅니다.")
        if job["kind"] == "hwp":
            issues = output_plan.hwp_review_issues(result, job["parameters"].get("template_key"))
            if issues:
                fail("hwp_review_blocked", issues[0])
            if not body.layout_confirmed or body.output_sha256 != result.get("sha256"):
                fail("layout_review_required", "생성 HWP를 열어 본문·표·페이지 배치를 확인하세요.")
    if body.action == "ready":
        deadline_errors = deadline_issues(ws["inputs"])
        if deadline_errors:
            fail("deadline_unavailable", deadline_errors[0], "공식 공고의 최신 마감일시를 확인하세요.")
        issues = blockers(ws["inputs"]) + input_file_issues(ws["inputs"])
        if (
            issues
            or result.get("warnings")
            or job["kind"] != "package"
            or ws["decision"] != "participate"
        ):
            fail("not_ready", "미확인 항목이 남아 제출 준비를 완료할 수 없습니다.")
        for included in result.get("included_jobs") or []:
            latest = conn.execute(
                select(reviews.c.action)
                .where(reviews.c.job_id == included, reviews.c.input_version == ws["version"])
                .order_by(reviews.c.created_at.desc(), reviews.c.id.desc())
                .limit(1)
            ).scalar()
            if latest != "approved":
                fail("artifact_review_changed", "패키지에 포함된 생성물의 승인이 변경되었습니다.")
        if not package_current(conn, ws, job):
            fail("package_changed", "최신 승인 파일로 패키지를 다시 생성하고 확인하세요.")
    audit(
        conn,
        ws,
        body.action,
        body.note,
        {"sha256": result.get("sha256"), "previous_review_id": body.expected_review_id,
         "layout_confirmed": body.layout_confirmed if job["kind"] == "hwp" else False},
        body.job_id,
    )
