"""Structured proposal generation; logical body coverage is independent of COM success."""
import hashlib
from pathlib import Path

from api.hwp_worker.layout import compile_markdown
from api.parsing.hwp_readback import verify_readback
from api.parsing.hwp_validation import read_hwp_output, validate_hwp_content
from api.services.hwp_agent_client import HwpAgentClient, HwpAgentError
from api.workspace.document_drafts import proposal_sections
from api.workspace.hwp_inspection import template_file


def proposal_text(inputs: dict) -> str:
    texts = [s.get("text", "") for s in proposal_sections(inputs) if s.get("text", "").strip()]
    main = [text for text in texts if text.lstrip().startswith("# ")]
    notes = [text for text in texts if not text.lstrip().startswith("# ")]
    if main and notes:
        return "\n\n<!-- page -->\n\n".join(main) + "\n\n<!-- page -->\n\n# 추가 검토 의견\n\n" + "\n\n".join(notes)
    return "\n\n".join(texts)


def validate_created(report: dict, output: Path, layout, base_hash: str | None) -> str:
    expected = [{"field": f, "occurrence": 0} for f in layout.fields()]
    if (report.get("output_path") != str(output) or report.get("base_sha256") != base_hash
        or report.get("fields") != layout.fields() or report.get("field_occurrences") != expected
        or report.get("layout_sha256") != layout.checksum()
        or report.get("lifecycle") != ["opened" if base_hash else "created", "saved", "closed", "reopened", "closed", "quit"]):
        raise ValueError("invalid_created_template_evidence")
    content = read_hwp_output(output)
    validate_hwp_content(content, ".hwp")
    checksum = hashlib.sha256(content).hexdigest()
    if checksum != report.get("sha256"):
        raise ValueError("created_template_hash_mismatch")
    return checksum


def run_layout_hwp(job: dict, preview: dict, folder: Path) -> dict:
    from api.workspace.service import blockers, fail

    body = proposal_text(job["snapshot"])
    try:
        layout, values, manifest = compile_markdown(body)
    except ValueError as exc:
        fail("unsupported_proposal_layout", "제안서 서식을 변환할 수 없습니다.", str(exc))
    mappings = preview["mappings"]
    if len(mappings) != 1 or mappings[0]["context_path"] != "proposal.body" or not preview["body_mapped"]:
        fail("layout_mapping_invalid", "서식 템플릿에는 필수 proposal.body 매핑 하나만 사용하세요.")
    base, base_hash = template_file(preview["template"])
    working = folder.resolve() / "working-template.hwp"
    output = folder.resolve() / "draft.hwp"
    client = HwpAgentClient(retries=1, timeout_s=120)
    try:
        created = client.create_template(operation_id=job["id"] + "-layout", output_path=str(working),
                                         base_template_path=str(base), layout=layout.model_dump(),
                                         visible=job.get("parameters", {}).get("visible", False))
        working_hash = validate_created(created, working, layout, base_hash)
        result = client.put_fields(template_path=str(working), output_path=str(output), values=values,
                                   operation_id=job["id"], render_pages=True,
                                   visible=job.get("parameters", {}).get("visible", False))
        content = read_hwp_output(output)
        validation = validate_hwp_content(content, ".hwp")
        checksum = hashlib.sha256(content).hexdigest()
        proof = verify_readback(result.raw, values, working_hash, checksum)
        if not proof or result.missing or hashlib.sha256(base.read_bytes()).hexdigest() != base_hash:
            raise ValueError("layout_body_or_template_mismatch")
        if result.output_path != str(output):
            raise ValueError("layout_output_path_mismatch")
        pages = result.raw.get("pages")
        if not isinstance(pages, list) or not 1 <= len(pages) <= 100:
            raise ValueError("layout_page_images_missing")
        for number, page in enumerate(pages, 1):
            path = Path(page["path"])
            if (page["number"] != number or path.is_symlink() or path.suffix != ".png"
                or not path.resolve().is_relative_to(output.parent / "draft-pages")
                or hashlib.sha256(path.read_bytes()).hexdigest() != page["sha256"]):
                raise ValueError("layout_page_image_invalid")
    except HwpAgentError as exc:
        fail(exc.code, "한글 서식 생성에 실패했습니다.", f"한글 단계: {exc.stage or '연결·응답 확인'}. 파일 확인 후 복구하세요.", status=502)
    except (ValueError, OSError, KeyError, TypeError):
        fail("layout_verification_failed", "서식 생성 파일·본문·페이지 대조에 실패했습니다.", "생성 기록과 한글 파일을 확인하세요.", status=502)
    warnings = blockers(job["snapshot"])
    if result.remaining_placeholders:
        warnings.append("미입력 또는 검증필요 내용이 남아 있습니다.")
    warnings.append("한글 페이지 배치는 담당자 검토가 필요합니다.")
    return {"artifact": str(output), "sha256": checksum, "size": len(content), "warnings": warnings,
            "input_values": values, "logical_input": body, "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "body_manifest": manifest, "layout": layout.model_dump(), "layout_sha256": layout.checksum(),
            "template_sha256": base_hash, "working_template_sha256": working_hash,
            "template_version": preview["template"].get("template_version"), "template_creation": created,
            "fields": layout.fields(), "replaced": result.replaced, "missing": [], "required_missing": [],
            "remaining_placeholders": result.remaining_placeholders, "pages": pages, "page_count": len(pages),
            "validation": {**validation, **proof, "body_coverage": "passed", "layout_review": "required"},
            "verified": True, "worker_verification": result.raw["verification"]}
