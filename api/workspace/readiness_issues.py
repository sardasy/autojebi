"""Typed readiness reasons and their Korean compatibility projection.

Predicates emit codes at the point of decision; strings never drive decisions.
This leaf module must not import workspace services or mutate stored inputs.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class IssueCode(StrEnum):
    SOURCE_CHANGED = "source_changed"
    DEADLINE_UNKNOWN = "deadline_unknown"
    DEADLINE_TIMEZONE_UNKNOWN = "deadline_timezone_unknown"
    DEADLINE_PASSED = "deadline_passed"
    ATTACHMENT_MISSING = "attachment_missing"
    ATTACHMENT_UNREAD = "attachment_unread"
    SOURCE_NEED_UNRESOLVED = "source_need_unresolved"
    FORM_REVIEW_REQUIRED = "form_review_required"
    FORM_LAYOUT_STALE = "form_layout_stale"
    FORM_REFERENCE_STALE = "form_reference_stale"
    WRITING_OUTPUT_MISSING = "writing_output_missing"
    SPEC_REVIEW_REQUIRED = "spec_review_required"
    WRITING_PLAN_STALE = "writing_plan_stale"
    WRITING_TARGET_EMPTY = "writing_target_empty"
    SOURCE_REVIEW_REQUIRED = "source_review_required"
    ASSET_STALE = "asset_stale"
    ASSET_DISABLED = "asset_disabled"
    ASSET_EXPIRED = "asset_expired"
    ASSET_NOT_YET_VALID = "asset_not_yet_valid"
    ASSET_VALIDITY_UNKNOWN = "asset_validity_unknown"
    ASSET_SUBJECT_MISMATCH = "asset_subject_mismatch"
    SOURCE_EXTRACTION_REQUIRED = "source_extraction_required"
    EVIDENCE_UNCONFIRMED = "evidence_unconfirmed"
    REQUIREMENTS_MISSING = "requirements_missing"
    REQUIREMENT_REVIEW_REQUIRED = "requirement_review_required"
    REQUIREMENT_COMPLIANCE_REQUIRED = "requirement_compliance_required"
    COMMERCIAL_REVIEW_REQUIRED = "commercial_review_required"
    PROPOSAL_REVIEW_REQUIRED = "proposal_review_required"
    PROPOSAL_COVERAGE_MISSING = "proposal_coverage_missing"
    SOURCE_CHECKSUM_MISSING = "source_checksum_missing"
    SOURCE_FILE_INVALID = "source_file_invalid"
    HWP_OUTPUT_MISSING = "hwp_output_missing"
    EXCEL_OUTPUT_MISSING = "excel_output_missing"
    ARTIFACT_REVIEW_REQUIRED = "artifact_review_required"
    ARTIFACT_WARNING = "artifact_warning"
    FORM_RETIRED = "form_retired"


# code -> (compatibility text template, actionable instruction)
CATALOG: dict[IssueCode, tuple[str, str]] = {
    IssueCode.SOURCE_CHANGED: ("원문/회사 정보가 변경됨: 동기화 필요", "최신 원문과 회사 정보를 동기화하세요."),
    IssueCode.DEADLINE_UNKNOWN: ("입찰 마감일시 미확인: 공식 공고에서 확인 필요", "공식 공고의 마감일시를 확인하세요."),
    IssueCode.DEADLINE_TIMEZONE_UNKNOWN: ("입찰 마감일시 시간대 미확인: 공식 공고에서 확인 필요", "마감일시의 시간대를 확인하세요."),
    IssueCode.DEADLINE_PASSED: ("입찰 마감 경과: 제출 준비 완료 불가, 최신 공고 확인 필요", "검토용으로 이용하고 최신 공고를 확인하세요."),
    IssueCode.ATTACHMENT_MISSING: ("공고 첨부 누락: {name}", "해당 첨부 원본을 확보하고 연결하세요."),
    IssueCode.ATTACHMENT_UNREAD: ("공고 첨부 본문 확인 필요: {name}", "추출 실패 위치와 원본을 확인하세요."),
    IssueCode.SOURCE_NEED_UNRESOLVED: ("별도 원문 확보·해당 여부 확인 필요: {name}", "별도 자료를 연결하거나 해당 여부를 검토하세요."),
    IssueCode.FORM_REVIEW_REQUIRED: ("원본 양식 작성값·근거 및 한글 배치 검토 필요", "작성값과 근거를 대조하고 한글 배치를 검토하세요."),
    IssueCode.FORM_LAYOUT_STALE: ("원본 양식 작성 사본의 실제 배치·내용 재검토 필요", "최신 작성 사본의 미입력 항목과 배치를 검토하세요."),
    IssueCode.FORM_REFERENCE_STALE: ("원본 양식 작성 근거 또는 위치 재검토 필요", "최신 원본과 작성 위치·근거를 다시 연결하세요."),
    IssueCode.WRITING_OUTPUT_MISSING: ("제출 양식 작성·검토 필요: {title}", "해당 원본 양식의 작성 사본을 완성하고 검토하세요."),
    IssueCode.SPEC_REVIEW_REQUIRED: ("필수 기술사양 검증·사람 검토 필요", "필수 기술사양의 근거와 충족 여부를 검토하세요."),
    IssueCode.WRITING_PLAN_STALE: ("공고 작성 대상 재확인 필요", "최신 공고의 작성 대상을 확인하세요."),
    IssueCode.WRITING_TARGET_EMPTY: ("작성 대상 미작성: {title}", "해당 작성 대상의 내용을 입력하세요."),
    IssueCode.SOURCE_REVIEW_REQUIRED: ("원문 전체 및 필수 요구사항 대조 확인 필요", "원문 전체와 필수 요구사항을 대조하세요."),
    IssueCode.ASSET_STALE: ("중앙 자료 변경: 다시 연결·검토 필요", "최신 회사 자료를 다시 연결하고 검토하세요."),
    IssueCode.ASSET_DISABLED: ("중앙 자료 비활성", "사용 가능한 최신 회사 자료를 연결하세요."),
    IssueCode.ASSET_EXPIRED: ("중앙 자료 유효기간 만료", "유효한 회사 자료를 확보하고 다시 검토하세요."),
    IssueCode.ASSET_NOT_YET_VALID: ("중앙 자료 발급일 미도래", "발급일과 해당 공고에 적용 가능한 기간을 확인하세요."),
    IssueCode.ASSET_VALIDITY_UNKNOWN: ("중앙 자료 유효기간 미확인", "자료의 발급일·만료일 또는 유효기간 없음을 확인하세요."),
    IssueCode.ASSET_SUBJECT_MISMATCH: ("중앙 자료 회사 주체 불일치·미확인", "공고에 참여하는 회사와 자료의 주체를 대조하세요."),
    IssueCode.SOURCE_EXTRACTION_REQUIRED: ("공고 원문 본문 추출/확인 필요", "원문 추출 결과와 누락·실패 영역을 확인하세요."),
    IssueCode.EVIDENCE_UNCONFIRMED: ("필수 증빙 미확인: {name}", "유효한 증빙을 연결하고 내용을 검토하세요."),
    IssueCode.REQUIREMENTS_MISSING: ("원문 근거가 있는 요구사항 등록 필요", "원문 인용에 연결된 요구사항을 등록하세요."),
    IssueCode.REQUIREMENT_REVIEW_REQUIRED: ("필수 요구사항 검토 필요: {text}", "요구사항의 원문 인용과 증빙을 검토하세요."),
    IssueCode.REQUIREMENT_COMPLIANCE_REQUIRED: ("필수 요구사항 충족 판정 필요: {text}", "담당자가 근거를 대조해 충족 여부를 판단하세요."),
    IssueCode.COMMERCIAL_REVIEW_REQUIRED: ("제안 총액의 원화 금액·증빙·인용 위치 재확인 필요", "제안 총액과 가격 근거를 다시 확인하세요."),
    IssueCode.PROPOSAL_REVIEW_REQUIRED: ("제안서 본문 작성 및 사실 확인 필요", "제안서 내용과 사실 근거를 검토하세요."),
    IssueCode.PROPOSAL_COVERAGE_MISSING: ("제안서 필수 요구사항 대응 누락: {text}", "누락된 요구사항을 해당 작성 항목에 연결하세요."),
    IssueCode.SOURCE_CHECKSUM_MISSING: ("원본 체크섬 확인 필요: {name}", "원본 해시가 있는 자료를 다시 등록하세요."),
    IssueCode.SOURCE_FILE_INVALID: ("원본 파일 무결성 확인 필요: {name}", "원본 파일의 존재와 해시를 확인하세요."),
    IssueCode.HWP_OUTPUT_MISSING: ("HWP 생성물 없음: {template_key}", "선택한 양식의 HWP 검토 사본을 생성하세요."),
    IssueCode.EXCEL_OUTPUT_MISSING: ("Excel 생성물 없음", "Excel 검토 사본을 생성하세요."),
    IssueCode.ARTIFACT_REVIEW_REQUIRED: ("생성물 검토 승인 필요: {job_id}", "해당 생성 파일과 근거를 검토하세요."),
    IssueCode.ARTIFACT_WARNING: ("{message}", "해당 생성물의 경고와 원본을 확인하세요."),
    IssueCode.FORM_RETIRED: ("정정 ZIP의 이전 작성본은 이력에 보존됩니다. 새 대상 작성·검토 필요", "최신 ZIP의 새 작성 대상을 선택하세요."),
}


class ReadinessIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: IssueCode
    scope: Literal["workspace", "notice", "attachment", "source_need", "document", "form",
                   "writing_target", "requirement", "checklist", "commercial", "proposal", "artifact"]
    entity_id: str | None = None
    blocking: bool = True
    message_params: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def discard_display_projection(cls, value: object) -> object:
        # Portable manifests can be read back, but supplied display strings must
        # never override code-based rendering or become a second decision source.
        if isinstance(value, dict):
            return {key: item for key, item in value.items() if key not in {"message", "next_action"}}
        return value

    @computed_field
    @property
    def message(self) -> str:
        message = CATALOG[self.code][0].format(**self.message_params)
        if self.code.value.startswith("asset_") and "name" in self.message_params:
            message += f": {self.message_params['name']}"
        return message

    @computed_field
    @property
    def next_action(self) -> str:
        return CATALOG[self.code][1]


def issue(code: IssueCode, scope: str, entity_id: str | None = None, **params: str) -> ReadinessIssue:
    return ReadinessIssue(code=code, scope=scope, entity_id=entity_id, message_params=params)


def render_blockers(issues: list[ReadinessIssue], *, deduplicate: bool = False) -> list[str]:
    # These producers historically collapsed repeated form messages. Keep all
    # entity-specific reasons in structured output without changing old clients.
    collapsed = {IssueCode.FORM_REVIEW_REQUIRED, IssueCode.FORM_LAYOUT_STALE,
                 IssueCode.FORM_REFERENCE_STALE, IssueCode.WRITING_OUTPUT_MISSING}
    seen: set[tuple[IssueCode, str]] = set()
    messages = []
    for item in issues:
        key = (item.code, item.message)
        if not item.blocking or (item.code in collapsed and key in seen):
            continue
        seen.add(key)
        messages.append(item.message)
    return list(dict.fromkeys(messages)) if deduplicate else messages
