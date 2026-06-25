from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import anthropic

from api.config import settings
from api.models.notices import DocumentChecklistItem

log = logging.getLogger(__name__)

READY_STATUSES = {"ready", "generated"}


def analyze_document_requirements(row: Any) -> dict[str, Any]:
    """Build the document automation payload for one notice.

    v1 keeps all data under analysis.document_automation so the workflow can
    stabilize before introducing a dedicated documents table.
    v2(M11) additionally preserves ``uploads[]`` and ``exports[]`` across
    re-analysis so user-uploaded files and generated Excel/HWP records survive.
    """
    analysis = dict(row["analysis"] or {})
    raw = dict(row["raw"] or {})
    assignee = str(row["assignee"] or "")

    existing = analysis.get("document_automation") or {}
    # 첨부(공고서·규격서) 본문을 판정 근거로 사용 — 메타데이터만으로 정해지던 한계 해소.
    attachments_text = _attachments_text(existing.get("uploads") or [])

    llm_payload, llm_error = _llm_suggestions(row, attachments_text)
    checklist = _merge_checklist(
        _rule_checklist(row, attachments_text),
        llm_payload.get("checklist", []) if isinstance(llm_payload, dict) else [],
        assignee,
    )
    checklist = _preserve_manual_updates(
        checklist,
        (existing.get("checklist") or []),
    )
    # v2 — uploads로 채워진 항목 status를 ready로 자동 승격 (수동 변경 보존 후 적용)
    checklist = _apply_uploads_to_checklist(checklist, existing.get("uploads") or [])

    drafts = _build_drafts(row, checklist, llm_payload, existing)
    existing_drafts = existing.get("drafts") if isinstance(existing, dict) else None
    if isinstance(existing_drafts, dict) and isinstance(existing_drafts.get("bid_form"), dict):
        drafts["bid_form"] = existing_drafts["bid_form"]

    risks = _dedupe_strings(
        _rule_risks(raw, analysis)
        + (llm_payload.get("risks", []) if isinstance(llm_payload, dict) else [])
    )
    errors: list[dict[str, Any]] = []
    if llm_error:
        errors.append({"stage": "document_llm", "detail": llm_error[:500]})

    missing = validate_checklist(checklist)
    return {
        "checklist": [item.model_dump() for item in checklist],
        "drafts": drafts,
        "risks": risks,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source": "rule+llm" if llm_payload else "rule",
        "ready_for_submission": len(missing) == 0,
        "missing_required": [item.model_dump() for item in missing],
        "errors": errors,
        # v2 — 분석 재실행 시에도 보존
        "uploads": list(existing.get("uploads") or []),
        "exports": list(existing.get("exports") or []),
    }


def _apply_uploads_to_checklist(
    checklist: list[DocumentChecklistItem],
    uploads: list[Any],
) -> list[DocumentChecklistItem]:
    """업로드된 파일이 매핑된 항목 status를 ready로 자동 승격 (M11).

    이미 generated/not_applicable 상태인 항목은 변경하지 않는다.
    수동으로 ready로 둔 항목은 그대로 유지.
    """
    upload_items: set[str] = {
        str(u.get("item_id"))
        for u in uploads
        if isinstance(u, dict) and u.get("item_id")
    }
    if not upload_items:
        return checklist
    for item in checklist:
        # 업로드는 "이 서류를 우리가 준비한다"는 확인 → 후보(not_applicable)도 필수+ready로 승격.
        if item.id in upload_items and item.status in {"needed", "blocked", "not_applicable"}:
            item.status = "ready"
            item.required = True
            parts = [p for p in item.source.split("+") if p]
            if "upload" not in parts:
                parts.append("upload")
            item.source = "+".join(parts)
    return checklist


def update_checklist_item(
    document_automation: dict[str, Any],
    item_id: str,
    *,
    status: str | None = None,
    owner: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    checklist = list(document_automation.get("checklist") or [])
    found = False
    for item in checklist:
        if not isinstance(item, dict) or item.get("id") != item_id:
            continue
        found = True
        if status is not None:
            item["status"] = status
        if owner is not None:
            item["owner"] = owner
        if note is not None:
            item["note"] = note
        item["source"] = _append_source(str(item.get("source") or "rule"), "manual")
        break
    if not found:
        raise KeyError(item_id)

    updated = dict(document_automation)
    updated["checklist"] = checklist
    _refresh_validation(updated)
    return updated


def validate_document_automation(document_automation: dict[str, Any]) -> dict[str, Any]:
    updated = dict(document_automation)
    _refresh_validation(updated)
    return updated


def validate_pre_compose(
    document_automation: dict[str, Any],
    *,
    spec_rows: list[dict[str, Any]],
    required_docs: list[dict[str, Any]] | None = None,
    values: dict[str, Any] | None = None,
    target_item_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """HWP/제안서 생성 전 품질 게이트.

    차단(error)의 권위는 **공고 원문 제출서류**(notice_required_documents)다:
    requirement_type=required 이고 즉시 제출 단계(bid/proposal/price)인데 사람이 아직
    확인(checked)하지 않은 항목이 있으면 차단한다. 공고 원문이 0건이면 차단하지 않는다.
    회사 공통/추정 체크리스트 미준비는 경고로만 노출한다(생성 대상은 제외).
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    targets = target_item_ids or set()

    if not spec_rows:
        errors.append(
            {
                "stage": "pre_compose.spec_items",
                "severity": "error",
                "detail": "규격 항목 추출 필요",
            }
        )

    # 공고 원문 제출서류 미확인 → 차단
    for rd in required_docs or []:
        if not isinstance(rd, dict):
            continue
        if (
            rd.get("requirement_type") == "required"
            and rd.get("submit_stage") in {"bid", "proposal", "price"}
            and not rd.get("checked")
        ):
            errors.append(
                {
                    "stage": "pre_compose.required_document",
                    "severity": "error",
                    "detail": f"공고 필수 제출서류 미확인: {rd.get('doc_name')}",
                    "item_id": rd.get("id"),
                }
            )

    # 회사 공통/추정 체크리스트 미준비 → 경고(차단 아님)
    checklist = document_automation.get("checklist") if isinstance(document_automation, dict) else None
    if isinstance(checklist, list):
        for item in checklist:
            if not isinstance(item, dict):
                continue
            if item.get("id") in targets:
                continue
            if item.get("required") is True and item.get("status") not in READY_STATUSES:
                warnings.append(
                    {
                        "stage": "pre_compose.company_prep",
                        "severity": "warning",
                        "detail": f"회사 준비서류 미준비: {item.get('name') or item.get('id')}",
                        "item_id": item.get("id"),
                    }
                )

    merged_values = {key: str(value) for key, value in (values or {}).items()}
    drafts = document_automation.get("drafts") if isinstance(document_automation, dict) else None
    if isinstance(drafts, dict):
        bid_values = drafts.get("bid_form_values")
        if isinstance(bid_values, dict):
            existing_values = bid_values.get("values")
            if isinstance(existing_values, dict):
                merged_values = {
                    **{key: str(value) for key, value in existing_values.items()},
                    **merged_values,
                }
            required = bid_values.get("required_placeholders") or []
            for key in required:
                if not merged_values.get(str(key)):
                    errors.append(
                        {
                            "stage": "pre_compose.required_value",
                            "severity": "error",
                            "detail": f"필수 작성값 누락: {key}",
                            "placeholder": str(key),
                        }
                    )

    for row in spec_rows:
        status = str(row.get("status") or "")
        confidence = float(row.get("confidence") or 0)
        if status == "candidate" or row.get("review_priority") == "high" or confidence < 0.75:
            warnings.append(
                {
                    "stage": "pre_compose.spec_review",
                    "severity": "warning",
                    "detail": f"검토 권장 규격 항목: {row.get('label') or row.get('item_key')}",
                    "item_key": row.get("item_key"),
                }
            )

    return errors, warnings


def attach_bid_form_result(
    analysis: dict[str, Any],
    *,
    template_path: str,
    output_path: str,
    replaced: list[str],
    missing: list[str],
    remaining_placeholders: list[str],
) -> dict[str, Any]:
    updated = dict(analysis or {})
    docs = dict(updated.get("document_automation") or {})
    drafts = dict(docs.get("drafts") or {})
    drafts["bid_form"] = {
        "kind": "hwp_autofill",
        "label": "입찰참가신청서 HWP 자동작성 결과",
        "template_path": template_path,
        "output_path": output_path,
        "replaced": replaced,
        "missing": missing,
        "remaining_placeholders": remaining_placeholders,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "review_note": "검토용 초안입니다. 나라장터 제출 전 담당자 확인이 필요합니다.",
    }
    docs["drafts"] = drafts

    checklist = list(docs.get("checklist") or [])
    for item in checklist:
        if isinstance(item, dict) and item.get("id") == "bid_form":
            item["status"] = "generated"
            item["source"] = _append_source(str(item.get("source") or "rule"), "hwp")
    docs["checklist"] = checklist
    _refresh_validation(docs)
    updated["document_automation"] = docs
    return updated


def validate_checklist(items: list[DocumentChecklistItem]) -> list[DocumentChecklistItem]:
    return [item for item in items if item.required and item.status not in READY_STATUSES]


ATTACHMENTS_TEXT_CAP = 12000


def _attachments_text(uploads: list[Any]) -> str:
    """업로드/첨부의 보존 본문(text_excerpt)을 파일명과 함께 모아 판정 코퍼스로 만든다.

    text_excerpt가 없으면 analysis_summary로 폴백. 총량은 ATTACHMENTS_TEXT_CAP로 제한.
    """
    parts: list[str] = []
    total = 0
    for u in uploads:
        if not isinstance(u, dict):
            continue
        excerpt = str(u.get("text_excerpt") or u.get("analysis_summary") or "").strip()
        if not excerpt:
            continue
        chunk = f"[{u.get('name') or '첨부'}]\n{excerpt}"
        if total + len(chunk) > ATTACHMENTS_TEXT_CAP:
            chunk = chunk[: max(0, ATTACHMENTS_TEXT_CAP - total)]
        if not chunk:
            break
        parts.append(chunk)
        total += len(chunk)
        if total >= ATTACHMENTS_TEXT_CAP:
            break
    return "\n\n".join(parts)


def _rule_checklist(row: Any, attachments_text: str = "") -> list[DocumentChecklistItem]:
    assignee = str(row["assignee"] or "")
    raw = dict(row["raw"] or {})
    analysis = dict(row["analysis"] or {})
    title = str(row["title"] or row["notice_no"] or "")
    joined = (
        " ".join(str(v) for v in raw.values() if v).lower()
        + " "
        + title.lower()
        + " "
        + attachments_text.lower()
    )

    # 생성 타깃(bid_form/technical_compliance)만 기본 required, 나머지는 "후보"(required=False).
    # 회사 공통/추정형은 공고 원문(notice_required_documents)이 1순위 권위이므로 공고 필수처럼
    # 보이지 않게 not_applicable 후보로 시작하고, 키워드/LLM이 확인하면 승격한다.
    items = [
        _item("bid_form", "입찰참가신청서", "bid_form", assignee,
              "HWP autofill 대상 기본 양식입니다.",
              required=True, status="needed", document_role="submit_required"),
        _item("technical_compliance", "규격대응표", "technical", assignee,
              "공고 요구사양과 제안 사양의 대응표 초안이 필요합니다.",
              required=True, status="needed", document_role="submit_required"),
        _item("business_registration", "사업자등록증", "company_common", assignee,
              "회사 공통 준비서류(후보) — 공고 원문에서 요구가 확인되면 필수로 승격됩니다.",
              required=False, status="not_applicable", document_role="internal_prep"),
        _item("corporate_seal", "법인등기/인감 관련 서류", "company_common", assignee,
              "회사 공통 준비서류(후보).",
              required=False, status="not_applicable", document_role="internal_prep"),
        _item("manufacturer_letter", "제조사 공급확약서", "qualification", assignee,
              "공급 가능성·제조사 권한 확인 후보입니다.",
              required=False, status="not_applicable", document_role="qualification_evidence"),
        _item("catalog", "카탈로그/기술자료", "technical", assignee,
              "추천 SKU·공고 사양 검토 후보입니다.",
              required=False, status="not_applicable", document_role="qualification_evidence"),
        _item("performance_record", "납품실적증명", "qualification", assignee,
              "실적 제한 여부 확인 후보입니다.",
              required=False, status="not_applicable", document_role="qualification_evidence"),
        _item("bid_bond", "보증보험/입찰보증 관련 서류", "price", assignee,
              "보증금·지급각서 조건 확인 후보입니다.",
              required=False, status="not_applicable", document_role="price_document"),
        _item("license_certificate", "자격/면허 증빙", "qualification", assignee,
              "지역/면허/자격 제한 확인 후보입니다.",
              required=False, status="not_applicable", document_role="qualification_evidence"),
    ]

    # 키워드가 본문/공고에 보이면 후보 → 필수로 승격(needed).
    if "실적" in joined or "납품실적" in joined:
        _promote(items, "performance_record", "공고문에 실적 조건 키워드가 있어 확인이 필요합니다.")
    if "보증" in joined or "입찰보증" in joined:
        _promote(items, "bid_bond", "공고문에 보증 조건 키워드가 있어 확인이 필요합니다.")
    if "면허" in joined or "자격" in joined or "license" in joined:
        _promote(items, "license_certificate", "공고문에 자격/면허 제한 키워드가 있어 확인이 필요합니다.")

    if analysis.get("bid_form"):
        for item in items:
            if item.id == "bid_form":
                item.status = "generated"
                item.source = "rule+hwp"
    return items


def _item(
    item_id: str,
    name: str,
    item_type: str,
    owner: str,
    reason: str,
    *,
    required: bool = True,
    status: str = "needed",
    document_role: str | None = None,
) -> DocumentChecklistItem:
    return DocumentChecklistItem(
        id=item_id,
        name=name,
        type=item_type,  # type: ignore[arg-type]
        required=required,
        status=status,  # type: ignore[arg-type]
        owner=owner or None,
        reason=reason,
        source="rule",
        document_role=document_role,  # type: ignore[arg-type]
    )


def _promote(items: list[DocumentChecklistItem], item_id: str, reason: str) -> None:
    """후보(required=False/not_applicable)를 확인 필요(required=True/needed)로 승격."""
    for item in items:
        if item.id == item_id:
            item.required = True
            if item.status == "not_applicable":
                item.status = "needed"
            item.reason = reason
            return


def _merge_checklist(
    base: list[DocumentChecklistItem],
    extra: list[Any],
    default_owner: str,
) -> list[DocumentChecklistItem]:
    by_id = {item.id: item for item in base}
    for raw_item in extra:
        if not isinstance(raw_item, dict):
            continue
        name = str(raw_item.get("name") or "").strip()
        if not name:
            continue
        item_id = _slug(str(raw_item.get("id") or name))
        if item_id in by_id:
            target = by_id[item_id]
            if "required" in raw_item:
                new_required = bool(raw_item.get("required"))
                target.required = new_required
                # status를 required 판정에 맞춰 동기화 (수동 변경은 이후 _preserve_manual_updates에서 보존)
                if new_required and target.status == "not_applicable":
                    target.status = "needed"
                elif not new_required and target.status in {"needed", "blocked"}:
                    target.status = "not_applicable"
            target.reason = str(raw_item.get("reason") or target.reason or "")
            role = raw_item.get("document_role")
            # 생성 타깃(입찰참가신청서·규격대응표)은 항상 제출서류 — LLM이 참고원문으로 강등 못 하게 보호.
            if role in _DOCUMENT_ROLES and item_id not in _PROTECTED_SUBMIT_IDS:
                target.document_role = role
            target.source = _append_source(target.source, "llm")
            continue
        item_type = str(raw_item.get("type") or "other")
        if item_type not in {
            "company_common",
            "bid_form",
            "technical",
            "qualification",
            "price",
            "contract",
            "other",
        }:
            item_type = "other"
        new_required = bool(raw_item.get("required", True))
        role = raw_item.get("document_role")
        by_id[item_id] = DocumentChecklistItem(
            id=item_id,
            name=name,
            type=item_type,  # type: ignore[arg-type]
            required=new_required,
            status="needed" if new_required else "not_applicable",
            owner=str(raw_item.get("owner") or default_owner or "") or None,
            reason=str(raw_item.get("reason") or "LLM이 공고문에서 추출한 제출서류입니다."),
            source="llm",
            due_hint=str(raw_item.get("due_hint") or "") or None,
            document_role=role if role in _DOCUMENT_ROLES else None,  # type: ignore[arg-type]
        )
    return list(by_id.values())


_DOCUMENT_ROLES = {
    "submit_required",
    "reference_only",
    "qualification_evidence",
    "price_document",
    "internal_prep",
}

# 생성 타깃 — 항상 submit_required(제출서류)로 유지하고 LLM 역할 강등에서 보호.
_PROTECTED_SUBMIT_IDS = {"bid_form", "technical_compliance"}


def _preserve_manual_updates(
    fresh: list[DocumentChecklistItem],
    previous: list[Any],
) -> list[DocumentChecklistItem]:
    prev_by_id = {p.get("id"): p for p in previous if isinstance(p, dict) and p.get("id")}
    for item in fresh:
        prev = prev_by_id.get(item.id)
        if not isinstance(prev, dict):
            continue
        # 사용자가 수동으로 바꾼 항목만 status/owner/note를 보존한다. 규칙/LLM이 파생한
        # status는 재평가가 갱신하도록 둔다(그렇지 않으면 한 번 정해진 필요/해당없음이 고정됨).
        # 업로드로 ready가 된 항목은 이후 _apply_uploads_to_checklist가 다시 승격한다.
        if "manual" not in str(prev.get("source") or ""):
            continue
        if "status" in prev:
            item.status = prev["status"]
        if "owner" in prev:
            item.owner = prev["owner"]
        if "note" in prev:
            item.note = prev["note"]
        item.source = _append_source(item.source, "manual")
    return fresh


def _build_drafts(
    row: Any,
    checklist: list[DocumentChecklistItem],
    llm_payload: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis = dict(row["analysis"] or {})
    raw = dict(row["raw"] or {})
    elec_spec = dict(analysis.get("elec_spec") or {})
    title = str(row["title"] or row["notice_no"] or "")
    top_sku_name = str(row.get("top_sku_name") or "") if hasattr(row, "get") else ""
    org_name = str(row.get("org_name") or raw.get("ntceInsttNm") or raw.get("dminsttNm") or "")
    close_date = row.get("close_date") if hasattr(row, "get") else None
    close_date_text = close_date.isoformat() if hasattr(close_date, "isoformat") else str(close_date or "")
    uploads = list((existing or {}).get("uploads") or [])

    technical_lines = [
        "| 항목 | 공고 요구사양 | 추출/추천 값 | 확인 |",
        "| --- | --- | --- | --- |",
    ]
    for key, label in [
        ("product_category", "품목"),
        ("quantity", "수량"),
        ("rated_voltage_kv", "정격전압(kV)"),
        ("rated_current_a", "정격전류(A)"),
        ("rated_power_kva", "정격용량(kVA)"),
        ("rated_power_kw", "정격출력(kW)"),
        ("protection_class", "보호등급"),
        ("standards", "규격"),
    ]:
        val = elec_spec.get(key)
        if isinstance(val, list):
            val = ", ".join(str(x) for x in val)
        technical_lines.append(f"| {label} | 공고문 확인 | {val or '-'} | 담당자 검토 |")
    if top_sku_name:
        technical_lines.append(f"| 추천 SKU | 제품 매칭 | {top_sku_name} | 담당자 검토 |")

    summary = [
        f"공고명: {title}",
        f"공고번호: {row['notice_no']}",
        f"기관: {raw.get('ntceInsttNm') or raw.get('dminsttNm') or '-'}",
        f"담당자: {row['assignee'] or '-'}",
        f"필수 서류: {sum(1 for item in checklist if item.required)}건",
        "주의: 검토용 초안이며 최종 제출 전 원문 공고와 나라장터 화면 확인이 필요합니다.",
    ]

    technical_content = "\n".join(technical_lines)
    upload_summaries = _upload_summaries(uploads)
    drafts = {
        "bid_form_values": {
            "kind": "json",
            "label": "HWP autofill 보강 입력값",
            "values": {
                "notice_no": str(row["notice_no"] or ""),
                "title": title,
                "org_name": org_name,
                "close_date": close_date_text,
                "category": str(row["category"] or ""),
                "assignee": str(row["assignee"] or ""),
                "fit_score": str(row["fit_score"] or 0),
                "top_sku_name": top_sku_name,
                "technical_compliance_summary": _compact_text(technical_content, 500),
                "uploaded_document_summary": upload_summaries,
            },
            "review_note": "회사 기본정보는 환경변수 또는 HWP 실행 모달 values에서 최종 보강합니다.",
        },
        "technical_compliance": {
            "kind": "markdown",
            "label": "규격대응표 초안",
            "content": technical_content,
        },
        "submission_summary": {
            "kind": "markdown",
            "label": "제출서류 요약 메모",
            "content": "\n".join(f"- {line}" for line in summary),
        },
    }
    if isinstance(llm_payload, dict) and isinstance(llm_payload.get("drafts"), dict):
        drafts.update(llm_payload["drafts"])
    return drafts


def _upload_summaries(uploads: list[Any]) -> str:
    lines: list[str] = []
    for item in uploads:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "upload")
        mapped = str(item.get("item_id") or item.get("detected_item_id") or "-")
        summary = str(item.get("analysis_summary") or "")
        lines.append(_compact_text(f"{name}: {mapped} {summary}".strip(), 180))
    return "\n".join(lines)


def _compact_text(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _rule_risks(raw: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    if analysis.get("risk_note"):
        risks.append(str(analysis["risk_note"]))
    close_date = raw.get("bidClseDt") or raw.get("close_date")
    if close_date:
        risks.append(f"마감일({close_date}) 전 제출서류 원본 확인이 필요합니다.")
    contract = str(raw.get("cntrctCnclsMthdNm") or "")
    if "수의" in contract or "지명" in contract:
        risks.append("계약방식이 수의/지명 성격이면 참가 가능 여부를 별도 확인해야 합니다.")
    return risks


def _llm_suggestions(row: Any, attachments_text: str = "") -> tuple[dict[str, Any], str | None]:
    if not settings.anthropic_api_key.strip():
        return {}, None
    try:
        raw = dict(row["raw"] or {})
        analysis = dict(row["analysis"] or {})
        prompt = (
            "한국 공공조달 입찰 공고의 제출서류 필요 여부를 판정하세요. "
            "특히 아래 '첨부 본문'(공고서·규격서)을 1차 근거로, 각 서류가 이 공고에서 "
            "실제로 필요한지(required true/false)를 결정하세요.\n"
            "출력은 JSON 객체 하나만 — 설명/마크다운/코드펜스 없이. "
            "JSON은 checklist, risks, drafts 키만 사용하세요. "
            "checklist 각 항목은 id,name,type,required(true/false),reason,document_role을 포함하세요.\n"
            "document_role은 다음 중 하나로 분류하세요: "
            "submit_required(실제 제출서류), reference_only(입찰공고문·규격서·평가준칙 등 검토용 원문 — 제출서류 아님), "
            "qualification_evidence(자격·실적·인증 증빙), price_document(가격제안서·산출내역서 등 가격 관련), "
            "internal_prep(사업자등록증·인감 등 회사 내부 공통 준비). "
            "입찰공고문/규격입찰설명서/구매규격서처럼 '검토해야 할 원문 첨부'는 reference_only로, "
            "required는 false로 두세요(제출 대상이 아님).\n"
            "다음 표준 id를 가능한 한 모두 평가하세요: bid_form, business_registration, "
            "corporate_seal, manufacturer_letter, catalog, technical_compliance, "
            "performance_record, bid_bond, license_certificate.\n"
            "본문에 납품실적 제한이 있으면 performance_record=true, 입찰보증/보증보험 요구가 "
            "있으면 bid_bond=true, 면허·자격·참가지역 제한이 있으면 license_certificate=true, "
            "근거가 없으면 false로 하고 reason에 본문 근거(또는 '근거 없음')를 적으세요. "
            "첨부에서 추가로 요구하는 서류가 있으면 새 id로 추가하세요.\n\n"
            f"공고명: {row['title'] or row['notice_no']}\n"
            f"raw: {json.dumps(raw, ensure_ascii=False)[:3000]}\n"
            f"analysis: {json.dumps(analysis, ensure_ascii=False)[:2000]}\n"
            f"첨부 본문:\n{attachments_text[:ATTACHMENTS_TEXT_CAP] if attachments_text else '(첨부 없음)'}"
        )
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=3000,  # 전체 체크리스트+한국어 reason JSON이 잘리지 않도록
            messages=[
                {"role": "user", "content": prompt},
                # assistant prefill "{" — Haiku가 산문 대신 JSON으로 응답하도록 강제.
                {"role": "assistant", "content": "{"},
            ],
        )
        body_text = "\n".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        return _safe_json_object("{" + body_text), None
    except Exception as exc:  # noqa: BLE001
        log.warning("[document_automation] LLM suggestion failed: %s", exc)
        return {}, str(exc)


def _safe_json_object(text: str) -> dict[str, Any]:
    cleaned = text.replace("```json", "").replace("```", "")
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        value = json.loads(cleaned[start : end + 1])
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _refresh_validation(document_automation: dict[str, Any]) -> None:
    parsed: list[DocumentChecklistItem] = []
    for item in document_automation.get("checklist") or []:
        try:
            parsed.append(DocumentChecklistItem.model_validate(item))
        except Exception:  # noqa: BLE001
            continue
    missing = validate_checklist(parsed)
    document_automation["missing_required"] = [item.model_dump() for item in missing]
    document_automation["ready_for_submission"] = len(missing) == 0


def _append_source(source: str, addition: str) -> str:
    parts = [part for part in source.split("+") if part]
    if addition not in parts:
        parts.append(addition)
    return "+".join(parts)


def _dedupe_strings(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _slug(value: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    return "_".join(part for part in out.split("_") if part)[:80] or "document"
