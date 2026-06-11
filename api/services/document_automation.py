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

    llm_payload, llm_error = _llm_suggestions(row)
    checklist = _merge_checklist(
        _rule_checklist(row),
        llm_payload.get("checklist", []) if isinstance(llm_payload, dict) else [],
        assignee,
    )
    existing = analysis.get("document_automation") or {}
    checklist = _preserve_manual_updates(
        checklist,
        (existing.get("checklist") or []),
    )
    # v2 — uploads로 채워진 항목 status를 ready로 자동 승격 (수동 변경 보존 후 적용)
    checklist = _apply_uploads_to_checklist(checklist, existing.get("uploads") or [])

    drafts = _build_drafts(row, checklist, llm_payload)
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
        if item.id in upload_items and item.status in {"needed", "blocked"}:
            item.status = "ready"
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


def _rule_checklist(row: Any) -> list[DocumentChecklistItem]:
    assignee = str(row["assignee"] or "")
    raw = dict(row["raw"] or {})
    analysis = dict(row["analysis"] or {})
    title = str(row["title"] or row["notice_no"] or "")
    joined = " ".join(str(v) for v in raw.values() if v).lower() + " " + title.lower()

    items = [
        _item("bid_form", "입찰참가신청서", "bid_form", assignee, "HWP autofill 대상 기본 양식입니다."),
        _item("business_registration", "사업자등록증", "company_common", assignee, "회사 공통 제출서류입니다."),
        _item("corporate_seal", "법인등기/인감 관련 서류", "company_common", assignee, "계약/입찰 공통 확인 서류입니다."),
        _item("manufacturer_letter", "제조사 공급확약서", "qualification", assignee, "공급 가능성과 제조사 권한 확인이 필요할 수 있습니다."),
        _item("catalog", "카탈로그/기술자료", "technical", assignee, "추천 SKU와 공고 사양을 검토해야 합니다."),
        _item("technical_compliance", "규격대응표", "technical", assignee, "공고 요구사양과 제안 사양의 대응표 초안이 필요합니다."),
        _item("performance_record", "납품실적증명", "qualification", assignee, "실적 제한 여부 확인이 필요합니다."),
        _item("bid_bond", "보증보험/입찰보증 관련 서류", "price", assignee, "입찰보증금 또는 지급각서 조건을 확인해야 합니다."),
        _item("license_certificate", "자격/면허 증빙", "qualification", assignee, "지역/면허/자격 제한을 확인해야 합니다."),
    ]

    if "실적" not in joined and "납품실적" not in joined:
        _set_optional(items, "performance_record", "공고문에서 실적 조건 키워드가 명확하지 않습니다.")
    if "보증" not in joined and "입찰보증" not in joined:
        _set_optional(items, "bid_bond", "보증 조건 키워드가 명확하지 않습니다.")
    if "면허" not in joined and "자격" not in joined and "license" not in joined:
        _set_optional(items, "license_certificate", "자격 제한은 grade 단계 결과와 함께 재확인합니다.")

    if analysis.get("bid_form"):
        for item in items:
            if item.id == "bid_form":
                item.status = "generated"
                item.source = "rule+hwp"
    return items


def _item(item_id: str, name: str, item_type: str, owner: str, reason: str) -> DocumentChecklistItem:
    return DocumentChecklistItem(
        id=item_id,
        name=name,
        type=item_type,  # type: ignore[arg-type]
        required=True,
        status="needed",
        owner=owner or None,
        reason=reason,
        source="rule",
    )


def _set_optional(items: list[DocumentChecklistItem], item_id: str, reason: str) -> None:
    for item in items:
        if item.id == item_id:
            item.required = False
            item.status = "not_applicable"
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
            by_id[item_id].required = bool(raw_item.get("required", by_id[item_id].required))
            by_id[item_id].reason = str(raw_item.get("reason") or by_id[item_id].reason or "")
            by_id[item_id].source = _append_source(by_id[item_id].source, "llm")
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
        by_id[item_id] = DocumentChecklistItem(
            id=item_id,
            name=name,
            type=item_type,  # type: ignore[arg-type]
            required=bool(raw_item.get("required", True)),
            status="needed",
            owner=str(raw_item.get("owner") or default_owner or "") or None,
            reason=str(raw_item.get("reason") or "LLM이 공고문에서 추출한 제출서류입니다."),
            source="llm",
            due_hint=str(raw_item.get("due_hint") or "") or None,
        )
    return list(by_id.values())


def _preserve_manual_updates(
    fresh: list[DocumentChecklistItem],
    previous: list[Any],
) -> list[DocumentChecklistItem]:
    prev_by_id = {p.get("id"): p for p in previous if isinstance(p, dict) and p.get("id")}
    for item in fresh:
        prev = prev_by_id.get(item.id)
        if not isinstance(prev, dict):
            continue
        if "status" in prev:
            item.status = prev["status"]
        if "owner" in prev:
            item.owner = prev["owner"]
        if "note" in prev:
            item.note = prev["note"]
        if "source" in prev and "manual" in str(prev.get("source")):
            item.source = _append_source(item.source, "manual")
    return fresh


def _build_drafts(row: Any, checklist: list[DocumentChecklistItem], llm_payload: dict[str, Any]) -> dict[str, Any]:
    analysis = dict(row["analysis"] or {})
    raw = dict(row["raw"] or {})
    elec_spec = dict(analysis.get("elec_spec") or {})
    title = str(row["title"] or row["notice_no"] or "")
    top_sku_name = str(row.get("top_sku_name") or "") if hasattr(row, "get") else ""

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

    drafts = {
        "bid_form_values": {
            "kind": "json",
            "label": "HWP autofill 보강 입력값",
            "values": {
                "notice_no": str(row["notice_no"] or ""),
                "title": title,
                "category": str(row["category"] or ""),
                "assignee": str(row["assignee"] or ""),
                "fit_score": str(row["fit_score"] or 0),
            },
            "review_note": "회사 기본정보는 환경변수 또는 HWP 실행 모달 values에서 최종 보강합니다.",
        },
        "technical_compliance": {
            "kind": "markdown",
            "label": "규격대응표 초안",
            "content": "\n".join(technical_lines),
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


def _llm_suggestions(row: Any) -> tuple[dict[str, Any], str | None]:
    if not settings.anthropic_api_key.strip():
        return {}, None
    try:
        raw = dict(row["raw"] or {})
        analysis = dict(row["analysis"] or {})
        prompt = (
            "한국 공공조달 입찰 공고의 제출서류를 JSON으로 추출하세요. "
            "반드시 checklist, risks, drafts 키만 사용하세요. "
            "checklist 항목은 id,name,type,required,reason,due_hint를 포함하세요.\n\n"
            f"공고명: {row['title'] or row['notice_no']}\n"
            f"raw: {json.dumps(raw, ensure_ascii=False)[:4000]}\n"
            f"analysis: {json.dumps(analysis, ensure_ascii=False)[:3000]}"
        )
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "\n".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        return _safe_json_object(text), None
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
