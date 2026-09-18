"""HWP jobs: field preview, template field inspection and put-fields generation."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select

from api.db.tables import document_field_mappings, hwp_templates
from api.hwp_worker.layout import compile_markdown
from api.parsing.hwp_readback import verify_readback
from api.parsing.hwp_validation import (
    OLE_MAGIC,
    HwpValidationError,
    read_hwp_output,
    validate_hwp_content,
)
from api.services.hwp_agent_client import (
    HwpAgentClient,
    HwpAgentError,
    validate_put_fields_response,
)
from api.services.hwp_fields import resolve_hwp_fields
from api.workspace.document_drafts import proposal_sections
from api.workspace.errors import fail
from api.workspace.hwp_inspection import inspect_template
from api.workspace.hwp_layout import proposal_text, run_layout_hwp
from api.workspace.service import blockers


def hwp_preview(conn: Any, inputs: dict, template_key: str) -> dict:
    template = (
        conn.execute(
            select(hwp_templates).where(
                hwp_templates.c.template_key == template_key, hwp_templates.c.active.is_(True)
            )
        )
        .mappings()
        .first()
    )
    if not template:
        fail("template_missing", "사용할 HWP 템플릿이 없습니다.")
    mappings = (
        conn.execute(
            select(document_field_mappings).where(
                document_field_mappings.c.template_id == template["id"],
                document_field_mappings.c.active.is_(True),
            )
        )
        .mappings()
        .all()
    )
    if not mappings:
        fail("mapping_missing", "템플릿 필드 매핑이 없습니다.")
    summary = "\n".join(
        f"{r['text']}: {r.get('proposed_value') or '[검증필요]'}" for r in inputs["requirements"]
    )
    proposal_body = "\n\n".join(s.get("text", "") for s in proposal_sections(inputs))
    if template["render_mode"] == "proposal_layout_v1":
        proposal_body = proposal_text(inputs)
        try:
            compile_markdown(proposal_body)
        except ValueError as exc:
            fail("unsupported_proposal_layout", "제안서에 지원하지 않는 서식이 있습니다.", f"입력 본문을 수정하세요: {exc}")
    context = {
        "notice": inputs["notice"],
        "company": inputs["company"],
        "grading": {},
        "spec_items": inputs["requirements"],
        "document_automation": {"drafts": {}},
        "proposal": {
            "technical_compliance_summary": summary,
            "spec_summary": summary,
            "body": proposal_body,
            "values": {"technical_compliance_summary": summary, "spec_summary": summary},
        },
    }
    resolved = resolve_hwp_fields(context=context, mappings=[dict(m) for m in mappings])
    return {
        "template": dict(template),
        "mappings": [dict(m) for m in mappings],
        "values": resolved.input_values,
        "required_missing": resolved.required_missing,
        "body_mapped": any(
            m["context_path"] == "proposal.body" and m["transform"] == "none" and m["required"]
            for m in mappings
        ),
    }


def run_hwp(engine: Any, job: dict, folder: Path) -> dict:
    with engine.begin() as conn:
        preview = hwp_preview(conn, job["snapshot"], job["parameters"]["template_key"])
        required_fields = list(
            conn.execute(
                select(document_field_mappings.c.hwp_field_name).where(
                    document_field_mappings.c.template_id == preview["template"]["id"],
                    document_field_mappings.c.active.is_(True),
                    document_field_mappings.c.required.is_(True),
                )
            ).scalars()
        )
    if preview["required_missing"]:
        fail("required_missing", "필수 입력 누락: " + ", ".join(preview["required_missing"]))
    if preview["template"]["kind"] == "proposal" and not preview["body_mapped"]:
        fail("proposal_body_unmapped", "제안서 전체 본문 필수 매핑이 없습니다.", "proposal.body를 변환 없음·필수 입력으로 연결하세요.")
    if not preview["values"]:
        fail("mapping_missing", "입력할 HWP 필드가 없습니다.")
    if not os.getenv("HWP_AGENT_TOKEN", "").strip():
        fail("worker_token_missing", "HWP Worker 인증 설정이 없습니다.")
    if preview["template"].get("render_mode") == "proposal_layout_v1":
        return run_layout_hwp(job, preview, folder)
    template_root = Path(os.getenv("HWP_TEMPLATE_ROOT", "data")).resolve()
    template_path = Path(preview["template"]["template_path"])
    if not template_path.is_absolute():
        template_path = template_root / template_path
    template_path = template_path.resolve()
    if not template_path.is_relative_to(template_root) or not template_path.is_file():
        fail("template_path", "허용된 템플릿 폴더에 파일이 없습니다.")
    if template_path.suffix.lower() not in {".hwp", ".hwpx"}:
        fail("template_path", "HWP 또는 HWPX 템플릿이 필요합니다.")
    template_content = template_path.read_bytes()
    template_sha256 = hashlib.sha256(template_content).hexdigest()
    if template_content.startswith(OLE_MAGIC):
        output_suffix = ".hwp"
    elif template_content.startswith(b"PK"):
        output_suffix = ".hwpx"
    else:
        fail("template_path", "템플릿의 HWP/HWPX 파일 형식을 확인할 수 없습니다.")
    output = folder.resolve() / ("draft" + output_suffix)
    if output.exists() or output.is_symlink() or output == template_path:
        fail("worker_output_exists", "출력 경로에 기존 파일이 있습니다. 새 작업으로 요청하세요.")
    client = HwpAgentClient(retries=1, timeout_s=120)
    if not client.health():
        fail(
            "worker_offline",
            "HWP Worker에 연결할 수 없습니다.",
            "Worker를 실행한 뒤 다시 요청하세요.",
        )
    try:
        inspection = inspect_template(preview["template"], preview["mappings"], client)
        if not inspection["inspection_passed"]:
            fail("template_fields_missing", "실제 템플릿의 필수 필드가 없습니다.", "템플릿 필드 검사 결과를 확인하세요.")
        result = client.put_fields(
            template_path=str(template_path),
            output_path=str(output),
            values=preview["values"],
            visible=job["parameters"].get("visible", False),
        )
        report = validate_put_fields_response(
            {
                **result.raw,
                "output_path": result.output_path,
                "replaced": result.replaced,
                "missing": result.missing,
                "remaining_placeholders": result.remaining_placeholders,
            },
            list(preview["values"]),
        )
    except HwpAgentError:
        fail(
            "worker_invalid_response",
            "HWP Worker 응답 또는 필드 처리 보고를 확인할 수 없습니다.",
            status=502,
        )
    if Path(result.output_path).resolve() != output.resolve():
        fail("worker_output_path", "Worker가 요청과 다른 경로를 반환했습니다.")
    if hashlib.sha256(template_path.read_bytes()).hexdigest() != template_sha256:
        fail("template_changed", "HWP 생성 중 템플릿이 변경되었습니다.", status=502)
    try:
        content = read_hwp_output(output)
        validation = validate_hwp_content(content, output.suffix)
        validation["field_partition"] = "passed"
        saved_verification = verify_readback(
            result.raw, preview["values"], template_sha256, hashlib.sha256(content).hexdigest()
        )
        if saved_verification:
            validation.update(saved_verification)
    except (HwpValidationError, OSError):
        fail(
            "worker_invalid_document",
            "생성 파일의 문서 구조 또는 저장된 필드값을 검증하지 못했습니다.",
            "파일 형식·필드 목록·저장값·Worker 검증 보고를 확인하세요.",
            status=502,
        )
    warnings = blockers(job["snapshot"])
    if not saved_verification:
        warnings.append(
            "문서 구조만 확인된 초안입니다. 실제 필드 목록·저장값 재조회 및 COM 실행 검증이 필요합니다."
        )
    if saved_verification and set(report.fields or []) - set(preview["values"]):
        warnings.append("입력 매핑이 없는 템플릿 필드가 있습니다. 기본값과 작성 대상을 확인하세요.")
    if result.missing or result.remaining_placeholders:
        warnings.append("템플릿 필드 누락 또는 미입력 항목이 있습니다.")
    required_missing = sorted(
        set(required_fields) & (set(result.missing) | set(result.remaining_placeholders))
    )
    # Hash the same bytes that passed validation, not a second read of worker output.
    return {
        "artifact": str(output),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "warnings": warnings,
        "input_values": preview["values"],
        "expected_fields": list(preview["values"]),
        "fields": report.fields,
        "replaced": result.replaced,
        "required_missing": required_missing,
        "missing": result.missing,
        "remaining_placeholders": result.remaining_placeholders,
        "validation": validation,
        "verified": bool(saved_verification),
        "worker_verification": result.raw.get("verification"),
        "template_version": preview["template"].get("template_version"),
        "template_sha256": template_sha256,
    }
