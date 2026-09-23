from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, computed_field, field_validator

from api.models.notices import NoticeUpsertRequest
from api.workspace.readiness_issues import ReadinessIssue

JobKind = Literal[
    "fetch",
    "analyze",
    "grade",
    "extract",
    "proposal",
    "verify",
    "excel",
    "hwp",
    "hwp_inspect",
    "package",
    "notify",
    "spec_index",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VersionRequest(StrictModel):
    version: int = Field(ge=1)


class WorkspaceNoticeRequest(NoticeUpsertRequest):
    org_name: str | None = Field(default=None, max_length=500)
    close_date: datetime | None = None

    @field_validator("close_date")
    @classmethod
    def aware_deadline(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("마감일시는 시간대와 함께 입력하세요.")
        return value


class JobRequest(StrictModel):
    kind: JobKind
    input_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=100)
    template_key: str = Field(default="bid_form", max_length=100)
    visible: bool = False


class CandidateSelection(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=4000)
    start: int = Field(ge=0)
    locator: str = Field(min_length=1, max_length=200)


class AdoptRequirements(VersionRequest):
    idempotency_key: str = Field(min_length=1, max_length=100)
    items: list[CandidateSelection] = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)


class SourceNeedResolution(StrictModel):
    id: str
    state: Literal["missing", "linked", "not_applicable"]
    document_id: str = ""
    resolution_quote: str = Field(default="", max_length=4000)
    locator: str = Field(default="", max_length=2000)
    note: str = Field(min_length=1, max_length=2000)


class SourceNeedsRequest(VersionRequest):
    items: list[SourceNeedResolution] = Field(min_length=1, max_length=50)


class DecisionRequest(VersionRequest):
    decision: Literal["pending", "participate", "hold", "decline"]
    note: str = Field(min_length=1, max_length=2000)


class DocumentReview(VersionRequest):
    role: Literal["company_evidence", "product_evidence", "notice_source"]
    confirmed: bool
    note: str = Field(min_length=1, max_length=2000)
    checklist_id: str | None = None


class TextRequest(VersionRequest):
    text: str = Field(min_length=1, max_length=200000)
    note: str = Field(min_length=1, max_length=2000)


class SourceLinkRequest(VersionRequest):
    attachment_index: int = Field(ge=1, le=10, strict=True)
    note: str = Field(min_length=1, max_length=2000)


class SourceAttachmentRecord(BaseModel):
    index: int
    name: str
    url: str
    document_ids: list[str]
    state: Literal["missing", "unread", "ready"]


class CommercialRequest(VersionRequest):
    offer_price: float = Field(gt=0, allow_inf_nan=False, strict=True)
    quantity: int = Field(gt=0, strict=True)
    document_id: str = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=4000)
    locator: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=2000)


class RequirementRequest(VersionRequest):
    specification: dict[str, Any] | None = None

    @field_validator("specification")
    @classmethod
    def validate_specification(cls, value):
        if value is not None:
            from api.specifications.models import Candidate
            return Candidate.model_validate(value).model_dump()
        return value
    id: str | None = None
    text: str = Field(min_length=1, max_length=4000)
    document_id: str
    quote: str = Field(min_length=1, max_length=4000)
    locator: str = Field(min_length=1, max_length=200)
    category: Literal["technical", "qualification", "document", "schedule"]
    mandatory: bool = True
    proposed_value: str = Field(default="", max_length=4000)
    evidence_id: str | None = None
    evidence_quote: str = Field(default="", max_length=4000)
    evidence_locator: str = Field(default="", max_length=200)
    review_status: Literal["pending", "accepted", "rejected"] = "pending"
    compliance: Literal["meets", "does_not_meet", "unassessed"] = "unassessed"
    proposal_disposition: Literal["include", "evidence_only"] = "include"
    proposal_note: str = Field(default="", max_length=2000)


class ReviewRequest(VersionRequest):
    action: Literal["approved", "rejected", "ready"]
    job_id: str
    note: str = Field(min_length=1, max_length=2000)
    expected_review_id: str | None = None
    output_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    layout_confirmed: bool = False


class OutputPlanRequest(VersionRequest):
    template_keys: list[str] = Field(min_length=1, max_length=20)
    note: str = Field(min_length=1, max_length=2000)


class RecoveryRequest(VersionRequest):
    idempotency_key: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)
    external_state_confirmed: bool = False
    visible: bool = False


class ReferenceDraft(TextRequest):
    requirement_id: str
    document_id: str
    quote: str = Field(min_length=1, max_length=200000)


class DraftReference(StrictModel):
    document_id: str
    quote: str = Field(min_length=1, max_length=20000)


class WebReference(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    quote: str = Field(min_length=1, max_length=20000)

    @field_validator("url")
    @classmethod
    def no_credentials(cls, value: HttpUrl) -> HttpUrl:
        if value.username or value.password:
            raise ValueError("Credentials are not allowed in reference URLs")
        return value


class DocumentDraft(TextRequest):
    draft_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    idempotency_key: str = Field(min_length=1, max_length=100)
    document_kind: Literal["qualitative_proposal", "bid_document", "other_document"]
    title: str = Field(min_length=1, max_length=200)
    references: list[DraftReference] = Field(default_factory=list, max_length=30)
    web_references: list[WebReference] = Field(default_factory=list, max_length=30)


class WritingPlanItem(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    title: str = Field(min_length=1, max_length=200)
    document_kind: Literal["qualitative_proposal", "bid_document", "other_document"]
    action: Literal["write", "attach", "electronic"]
    document_id: str
    quote: str = Field(min_length=1, max_length=20000)


class WritingPlanRequest(VersionRequest):
    items: list[WritingPlanItem] = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)


class SectionReview(TextRequest):
    approved: bool | None
    requirement_ids: list[str] | None = None
    evidence_ids: list[str] | None = None


class JobRecord(BaseModel):
    id: str
    notice_no: str
    kind: str
    input_version: int
    status: str
    quality: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @computed_field
    @property
    def execution_lane(self) -> str:
        from api.workspace.lanes import lane_for
        return lane_for(self.kind)


class WorkspaceRecord(BaseModel):
    notice_brief: dict[str, Any] = Field(default_factory=dict)
    spec_compliance: str = "미확인"
    unresolved_spec_count: int = 0
    spec_source_complete: bool = False
    writing_plan_current: bool = False
    notice_no: str
    version: int
    decision: str
    inputs: dict[str, Any]
    blockers: list[str]
    readiness_issues: list[ReadinessIssue] = Field(default_factory=list)
    readiness_checked_at: datetime | None = None
    next_action: str
    jobs: list[JobRecord]
    reviews: list[dict[str, Any]]
    source_changed: bool
    ready: bool
    proposal_coverage: dict[str, Any] = Field(default_factory=dict)
    source_attachments: list[SourceAttachmentRecord] = Field(default_factory=list)
    source_needs: list[dict[str, Any]] = Field(default_factory=list)
