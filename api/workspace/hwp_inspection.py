"""Template inspection identities never contain company values or template readback text."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from api.parsing.hwp_validation import HwpValidationError, read_hwp_output, validate_hwp_content
from api.services.hwp_agent_client import HwpAgentClient, HwpAgentError
from api.workspace.errors import WorkspaceError
from api.workspace.service import fail


def template_file(template: dict) -> tuple[Path, str]:
    root = Path(os.getenv("HWP_TEMPLATE_ROOT", "data")).resolve()
    path = Path(template["template_path"])
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        fail("template_path", "허용된 템플릿 폴더에 파일이 없습니다.")
    try:
        content = read_hwp_output(path)
        validate_hwp_content(content, path.suffix.lower())
        return path, hashlib.sha256(content).hexdigest()
    except (OSError, HwpValidationError):
        fail("template_path", "템플릿의 HWP/HWPX 형식을 확인할 수 없습니다.")


def mapping_hash(template: dict, mappings: list[dict]) -> str:
    columns = (
        "hwp_field_name",
        "context_path",
        "value_type",
        "required",
        "default_value",
        "transform",
        "sort_order",
        "active",
    )
    value = {
        "version": template.get("template_version"),
        "kind": template.get("kind"),
        "key": template.get("template_key"),
        "render_mode": template.get("render_mode", "fields"),
        "mappings": sorted(
            [{k: m.get(k) for k in columns} for m in mappings], key=lambda m: m["hwp_field_name"]
        ),
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def inspect_template(template: dict, mappings: list[dict], client: Any = None, *,
                     visible: bool = False, operation_id: str | None = None) -> dict:
    path, checksum = template_file(template)
    client = client or HwpAgentClient(retries=1, timeout_s=120)
    if not client.health():
        fail(
            "worker_offline",
            "HWP Worker 복구·연결 상태 확인이 필요합니다.",
            "필수조건에서 Worker 상태를 확인하세요.",
        )
    try:
        options = {}
        if visible:
            options["visible"] = True
        if operation_id:
            options["operation_id"] = operation_id
        report = client.inspect_fields(str(path), **options)
    except HwpAgentError:
        diagnosis = HwpAgentClient(retries=1, timeout_s=3).diagnostics()
        operation = diagnosis.get("operation", {})
        raise WorkspaceError(502, {"code": "worker_inspection_failed",
            "message": "실제 템플릿 필드 조회를 완료하지 못했습니다.",
            "next_action": "Worker와 한글 창을 확인한 뒤 복구 절차를 진행하세요.",
            "operation": operation if operation.get("operation_id") == operation_id else {},
            "recovery_required": diagnosis.get("recovery_required", False)}) from None
    if (
        report["sha256"] != checksum
        or hashlib.sha256(read_hwp_output(path)).hexdigest() != checksum
    ):
        fail("template_changed", "필드 검사 중 템플릿이 변경되었습니다.")
    expected = {m["hwp_field_name"] for m in mappings}
    required = {m["hwp_field_name"] for m in mappings if m.get("required")}
    actual = set(report["fields"])
    missing = sorted(required - actual)
    return {
        "template_key": template.get("template_key"),
        "template_sha256": checksum,
        "mapping_sha256": mapping_hash(template, mappings),
        "fields": report["fields"],
        "field_occurrences": report["field_occurrences"],
        "required_missing": missing,
        "missing": sorted(expected - actual),
        "unmapped": sorted(actual - expected),
        "inspection_passed": bool(actual) and not missing,
        "warnings": (["실제 템플릿 필수 필드 누락: " + ", ".join(missing)] if missing else [])
        + (["DB 매핑이 없는 템플릿 필드가 있습니다."] if actual - expected else [])
        + (["선택 입력 필드가 템플릿에 없습니다."] if expected - actual - required else [])
        + (["템플릿에 입력 필드가 없습니다."] if not actual else []),
    }
