"""Versioned output selection and artifact review requirements."""
from __future__ import annotations

import copy
import re
from typing import Any

from sqlalchemy import select

from api.db.tables import hwp_templates
from api.workspace.errors import HANDLED_ERRORS

LAYOUT_WARNING = "한글 페이지 배치는 담당자 검토가 필요합니다."


def template_keys(inputs: dict) -> list[str]:
    plan = inputs.get("output_plan")
    return list(plan["template_keys"]) if plan else ["bid_form", "proposal"]


def save(conn: Any, notice_no: str, body: Any) -> None:
    from api.workspace import service

    ws = service.load(conn, notice_no, body.version)
    service.assert_source_current(conn, ws)
    keys = sorted(set(body.template_keys))
    available = set(conn.execute(select(hwp_templates.c.template_key).where(
        hwp_templates.c.active.is_(True))).scalars())
    if not set(keys) <= available:
        service.fail("output_template_unavailable", "등록된 활성 HWP 서식을 선택하세요.", status=422)
    if not body.note.strip():
        service.fail("note_required", "출력 서류 선택 근거를 입력하세요.", status=422)
    if (ws["inputs"].get("output_plan") or {}).get("template_keys") == keys:
        return
    inputs = copy.deepcopy(ws["inputs"])
    inputs["output_plan"] = {"template_keys": keys, "note": body.note.strip()}
    service.change(conn, ws, inputs, "output_plan", body.note)


def hwp_review_issues(result: dict) -> list[str]:
    issues = []
    if not result.get("verified"):
        issues.append("한글 저장값 재조회 검증이 필요합니다.")
    if any(result.get(key) for key in ("missing", "required_missing", "remaining_placeholders")):
        issues.append("한글 미입력·필수 누락 항목을 먼저 수정하세요.")
    issues.extend(w for w in result.get("warnings", []) if w != LAYOUT_WARNING)
    return list(dict.fromkeys(issues))


def review_matches(job: dict, review: dict | None) -> bool:
    if not review or review["action"] != "approved":
        return False
    result = job.get("result") or {}
    details = review.get("details") or {}
    if details.get("sha256") != result.get("sha256"):
        return False
    return job["kind"] != "hwp" or bool(details.get("layout_confirmed") and not hwp_review_issues(result))


def selected_artifacts(records: list, inputs: dict) -> list:
    keys = set(template_keys(inputs))
    selected = {}
    for item in records:
        if item["status"] != "succeeded" or item["kind"] not in {"excel", "hwp"}:
            continue
        key = item["parameters"].get("template_key") if item["kind"] == "hwp" else None
        if item["kind"] == "hwp" and key not in keys:
            continue
        selected.setdefault((item["kind"], key), item)
    return list(selected.values())


def writing_output_issues(inputs: dict) -> list[str]:
    """Require an approved original form for each non-proposal writing target.

    A reference to a file containing several forms does not identify which form
    was filled. Match the target's full title to the original field context, then
    revalidate the entire filled document and its content-bound human approval.
    """
    from api.workspace.forms.filling import export_filling

    def title(value: str) -> str:
        heading = re.sub(
            r"^[<\[〈【]\s*서식\s*\d+(?:\s*[-–]\s*\d+)?\s*[>\]〉】]\s*",
            "", value,
        )
        return re.sub(r"\s+", "", heading).casefold()

    fillings = {f["document_id"]: f for f in inputs.get("form_fillings", [])}
    validated: dict[str, bool] = {}
    issues = []
    for item in (inputs.get("writing_plan") or {}).get("items", []):
        if item.get("action") != "write" or item.get("document_kind") == "qualitative_proposal":
            continue
        document_id = item.get("document_id", "")
        filling = fillings.get(document_id)
        expected = title(item.get("title", ""))
        matched = False
        if filling and expected:
            for field in filling.get("fields", []):
                mapping = field.get("mapping") or {}
                context = mapping.get("context", "")
                matched = title(context) == expected
                if mapping.get("kind") == "amount":
                    # These three headings are explicitly recognized by the
                    # original cost-form parser and share its canonical context.
                    matched = (expected in {"산출내역서", "산출공내역서", "공내역서"}
                               and context.startswith("산출내역서 · "))
                if matched:
                    break
        if matched and filling and filling.get("review_status") == "approved":
            if document_id not in validated:
                try:
                    _, _, report = export_filling(inputs, document_id)
                    review = report.get("review") or {}
                    validated[document_id] = bool(
                        report.get("review_status") == "approved"
                        and report.get("unfilled_count") == 0
                        and report.get("readback_verified")
                        and report.get("layout_verified")
                        and all(review.get(key) for key in
                                ("approved", "source_checked", "content_checked", "layout_checked"))
                    )
                except (*HANDLED_ERRORS, ValueError, KeyError, OSError):
                    validated[document_id] = False
            if validated[document_id]:
                continue
        issues.append(f"제출 양식 작성·검토 필요: {item.get('title') or item.get('id', '')}")
    return list(dict.fromkeys(issues))
