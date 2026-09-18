"""Read-only prerequisite checks; connection is not document or qualification approval."""

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from api.services.hwp_agent_client import HwpAgentClient
from api.workspace.errors import HANDLED_ERRORS
from api.workspace.execution import hwp_preview
from api.workspace.hwp_inspection import mapping_hash
from api.workspace.hwp_validation import HwpValidationError, read_hwp_output, validate_hwp_content
from api.workspace.provenance import requirement_valid
from api.workspace.source_inventory import source_inventory_issues, source_text_complete


class Prerequisite(BaseModel):
    code: str
    title: str
    state: Literal["checked", "blocked", "review"]
    detail: str
    action: str
    target: Literal["documents", "writing", "review", "company", "mappings", "recovery"]
    blocks_hwp: bool = False
    requirement_id: str | None = None


class Prerequisites(BaseModel):
    input_version: int
    template_key: str
    checked_at: str
    items: list[Prerequisite]
    hwp_request_available: bool
    required_missing: list[str]
    mapping_fields: list[str]


WORKER_MESSAGES = {
    "worker_running": ("작업 중", "한글 작업이 진행 중입니다.", "현재 실행이 끝난 뒤 다시 확인"),
    "worker_token_missing": (
        "인증 설정 필요",
        "32자 이상 HWP Worker 토큰 설정이 필요합니다.",
        "관리자에게 토큰 설정 요청",
    ),
    "worker_auth": (
        "인증 실패",
        "설정된 토큰으로 Worker 인증에 실패했습니다.",
        "API와 Worker의 토큰 일치 확인",
    ),
    "worker_recovery": (
        "복구 확인 필요",
        "이전 한글 작업의 종료 여부를 확인해야 합니다.",
        "한글 창·생성 파일 확인 후 관리자 복구 절차 진행",
    ),
    "worker_timeout": (
        "응답 시간 초과",
        "Worker 상태 응답이 지연되고 있습니다.",
        "한글 창과 Worker 상태 확인 후 다시 점검",
    ),
    "worker_connected": (
        "접속 확인",
        "상태 조회 성공. 실제 생성·저장값·문서 배치 검증과는 별개입니다.",
        "입력값 확인 후 검토용 초안 생성",
    ),
}


def check_prerequisites(
    conn: Any, inputs: dict, version: int, template_key: str, *, source_changed: bool = False,
    inspection: dict | None = None,
) -> Prerequisites:
    items = []

    def add(
        code: str,
        title: str,
        okay: Any,
        detail: str,
        action: str,
        target: str,
        blocks_hwp: bool = False,
        requirement_id: str | None = None,
    ) -> None:
        items.append(
            Prerequisite(
                code=code,
                title=title,
                state="checked" if okay else "blocked",
                detail=detail,
                action=action,
                target=target,
                blocks_hwp=blocks_hwp and not okay,
                requirement_id=requirement_id,
            )
        )

    if source_changed:
        add(
            "source_changed",
            "원본 자료 변경",
            False,
            "공고·회사정보·템플릿이 변경되었습니다.",
            "최신 상태 조회 후 원문 동기화",
            "documents",
            True,
        )

    documents = {d["id"]: d for d in inputs.get("documents", [])}
    source_issues = source_inventory_issues(inputs)
    source_ok = source_text_complete(inputs) and not source_issues and inputs.get("source_reviewed")
    add(
        "sources",
        "공고 원문",
        source_ok,
        "원문 전체 대조 확인"
        if source_ok
        else " · ".join(source_issues) or "원문 본문과 전체 대조 확인이 필요합니다.",
        "원문·변환본 확인",
        "documents",
    )
    qualifications = [
        r
        for r in inputs.get("requirements", [])
        if r.get("category") == "qualification" and r.get("mandatory", True)
    ]
    if not qualifications:
        add(
            "qualifications",
            "필수 참가 자격",
            False,
            "원문에서 필수 자격을 아직 확인하지 않았습니다.",
            "원문 요구사항 확인",
            "documents",
        )
    for req in qualifications:
        okay = requirement_valid(req, documents) and req.get("compliance") == "meets"
        add(
            "qualification_" + req["id"],
            req["text"],
            okay,
            "회사 증빙 연결·담당자 충족 판단 확인"
            if okay
            else "회사 증빙과 원문 인용을 연결하고 충족 여부를 검토해야 합니다.",
            "자격·증빙 검토",
            "documents",
            requirement_id=req["id"],
        )
    for role, title in [("company_evidence", "회사 증빙"), ("product_evidence", "제품 근거")]:
        count = sum(
            d.get("role") == role and d.get("confirmed") is True and bool(d.get("text", "").strip())
            for d in documents.values()
        )
        add(
            role,
            title,
            count > 0,
            f"본문이 있는 담당자 확인 자료 {count}개 · 개별 요구사항 충족은 별도 검토",
            "실제 자료 등록·확인",
            "documents",
        )
    references = [
        d
        for d in documents.values()
        if d.get("role") == "company_reference" and d.get("text", "").strip()
    ]
    add(
        "references",
        "기존 작성자료",
        bool(references),
        f"비교 가능한 자료 {len(references)}개 · 자격 증빙으로 인정하지 않음",
        "기존 제안서 등록",
        "writing",
    )
    missing, fields = [], []
    try:
        preview = hwp_preview(conn, inputs, template_key)
        if preview["template"].get("kind") == "proposal":
            add("hwp_body_mapping", "제안서 전체 본문 연결", preview["body_mapped"],
                "필수 본문 매핑 확인" if preview["body_mapped"] else "전체 본문을 변환 없음·필수 입력으로 연결해야 합니다.",
                "본문 필드 매핑 설정", "mappings", True)
        missing, fields = preview["required_missing"], list(preview["values"])
        labels = {
            "company_name": "회사명",
            "business_number": "사업자번호",
            "ceo_name": "대표자명",
            "address": "주소",
        }
        body_fields = {m["hwp_field_name"] for m in preview.get("mappings", [])
                       if m.get("context_path") == "proposal.body"}
        body_missing = bool(body_fields.intersection(missing))
        add(
            "hwp_values",
            "HWP 필수 작성값",
            bool(fields) and not missing,
            "필수 누락: " + (", ".join(labels.get(field, field) for field in missing) or "없음"),
            "제안서 본문 작성" if body_missing else "입력값·회사정보 확인",
            "writing" if body_missing else "company",
            True,
        )
        root = Path(os.getenv("HWP_TEMPLATE_ROOT", "data")).resolve()
        path = Path(preview["template"]["template_path"])
        path = (path if path.is_absolute() else root / path).resolve()
        valid = False
        if (
            path.is_relative_to(root)
            and path.is_file()
            and path.suffix.lower() in {".hwp", ".hwpx"}
        ):
            try:
                validate_hwp_content(read_hwp_output(path), path.suffix.lower())
                valid = True
            except (HwpValidationError, OSError):
                pass
        add(
            "hwp_template",
            "HWP 템플릿 파일",
            valid,
            "허용 폴더의 문서 구조 확인 · 내부 필드명은 생성 시 대조"
            if valid
            else "허용 폴더에 유효한 HWP/HWPX 템플릿이 없습니다.",
            "템플릿 파일·매핑 설정",
            "mappings",
            True,
        )
        matched = bool(valid and inspection
                       and inspection.get("template_sha256") == hashlib.sha256(read_hwp_output(path)).hexdigest()
                       and inspection.get("mapping_sha256") == mapping_hash(preview["template"], preview.get("mappings", [])))
        fields_ok = matched and inspection.get("inspection_passed") is True
        add("hwp_field_inspection", "실제 템플릿 필드 대조", fields_ok,
            "현재 파일·매핑 기준 필수 필드 확인" if fields_ok else "템플릿 필드 검사를 실행하고 필수 누락을 확인하세요.",
            "서류 확인에서 템플릿 필드 검사", "review", True)
    except (*HANDLED_ERRORS, ValueError, OSError):
        add(
            "hwp_mapping",
            "HWP 매핑",
            False,
            "활성 템플릿과 필드 매핑을 확인할 수 없습니다.",
            "템플릿·허용 변환 설정 확인",
            "mappings",
            True,
        )
    worker = HwpAgentClient(timeout_s=3, connect_timeout_s=2, retries=1).diagnostics()
    label, detail, action = WORKER_MESSAGES.get(
        worker["code"],
        (
            "연결 확인 필요",
            "Worker의 정상 상태를 확인할 수 없습니다.",
            "Worker 실행·주소·허용 폴더 확인",
        ),
    )
    add(
        worker["code"],
        "HWP Worker · " + label,
        worker["available"],
        detail,
        action,
        "recovery" if worker["recovery_required"] else "review",
        True,
    )
    items.append(
        Prerequisite(
            code="hwp_readback",
            title="실제 HWP 필드·배치",
            state="review",
            detail="템플릿 내부 필드, 저장값 재조회와 생성 파일 배치는 생성 후 확인합니다.",
            action="생성 결과 검토",
            target="review",
        )
    )
    return Prerequisites(
        input_version=version,
        template_key=template_key,
        checked_at=datetime.now(UTC).isoformat(),
        items=items,
        hwp_request_available=not any(i.blocks_hwp for i in items),
        required_missing=missing,
        mapping_fields=fields,
    )
