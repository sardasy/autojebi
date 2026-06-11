from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Category = Literal["HIL", "SW", "IGBT", "SCR", "수동소자", "ABB장비", "혼합", "비관련"]


class NoticeUpsertRequest(BaseModel):
    notice_no: str = Field(min_length=1)
    title: str | None = None
    source: str | None = Field(default="KJEBI", description="Data source identifier")
    raw: dict[str, Any] | None = None


class NoticeAnalyzeResponse(BaseModel):
    notice_no: str
    category: Category
    fit_score: int = Field(ge=0, le=100)
    assignee: str
    analysis: dict[str, Any]
    status: str


class NoticeRecord(BaseModel):
    notice_no: str
    title: str | None = None
    source: str | None = None
    raw: dict[str, Any] | None = None
    category: str
    fit_score: int
    assignee: str
    analysis: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    # G2B 수집 컬럼 (db/migrations/0001_collect_columns.sql) — 응답 top-level 노출
    bid_no: str | None = None
    bid_seq: str | None = None
    bid_type: str | None = None
    org_code: str | None = None
    org_name: str | None = None
    base_price: float | None = None
    open_date: datetime | None = None
    close_date: datetime | None = None
    collected_at: datetime | None = None
    # M3 — grading
    score_spec: float | None = None
    score_qual: float | None = None
    score_price: float | None = None
    score_total: float | None = None
    grade_reason: str | None = None
    risk_note: str | None = None
    top_sku: str | None = None
    top_sku_name: str | None = None
    sku_match_score: float | None = None
    graded_at: datetime | None = None


class NoticeListResponse(BaseModel):
    items: list[NoticeRecord]
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


Lifecycle = Literal["active", "closed", "unknown", "all"]
SortField = Literal["close_date", "updated_at", "base_price", "fit_score", "score_total"]
SortDirection = Literal["asc", "desc"]


class GradeRequest(BaseModel):
    alert: bool = True


class NoticeGradeResponse(BaseModel):
    notice_no: str
    score_spec: float
    score_qual: float
    score_price: float
    score_total: float
    top_sku: str | None = None
    top_sku_name: str | None = None
    grade_reason: str
    risk_note: str | None = None
    slack_delivered: bool
    status: str


class IngestRequest(BaseModel):
    source: str | None = None
    skus: list[dict[str, Any]] | None = None


class IngestResult(BaseModel):
    ingested: int
    collection: str


class NotifyRequest(BaseModel):
    dry_run: bool = True


class NotifyResponse(BaseModel):
    notice_no: str
    status: str
    delivered: bool


class AutofillFormRequest(BaseModel):
    template_path: str = Field(min_length=1, description="HWP template path (relative to milim-hwp-agent project).")
    output_path: str = Field(min_length=1, description="Output HWP path written by the agent.")
    values: dict[str, str] = Field(
        default_factory=dict,
        description="Placeholder values keyed without braces. Merged on top of bid_pipeline derived defaults.",
    )
    visible: bool = False


class AutofillFormResponse(BaseModel):
    notice_no: str
    status: str
    template_path: str
    output_path: str
    replaced: list[str]
    missing: list[str]
    remaining_placeholders: list[str]


DocumentItemType = Literal[
    "company_common",
    "bid_form",
    "technical",
    "qualification",
    "price",
    "contract",
    "other",
]

DocumentItemStatus = Literal[
    "needed",
    "ready",
    "generated",
    "blocked",
    "not_applicable",
]


class DocumentChecklistItem(BaseModel):
    id: str
    name: str
    type: DocumentItemType
    required: bool = True
    status: DocumentItemStatus = "needed"
    owner: str | None = None
    reason: str | None = None
    source: str = "rule"
    due_hint: str | None = None
    note: str | None = None


class DocumentAutomationResult(BaseModel):
    checklist: list[DocumentChecklistItem]
    drafts: dict[str, Any] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    generated_at: str
    source: str
    ready_for_submission: bool = False
    missing_required: list[DocumentChecklistItem] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class DocumentAutomationResponse(BaseModel):
    notice_no: str
    document_automation: DocumentAutomationResult


class ChecklistUpdateRequest(BaseModel):
    status: DocumentItemStatus | None = None
    owner: str | None = None
    note: str | None = None


class DocumentValidationResponse(BaseModel):
    notice_no: str
    ready_for_submission: bool
    missing_required: list[DocumentChecklistItem]
    checklist: list[DocumentChecklistItem]


# M11 — 서류 자동화 v2: 사용자 업로드 + Excel/HWP 내보내기

ExportKind = Literal["excel", "hwp"]


class UploadedDocument(BaseModel):
    id: str = Field(description="UUID4. 다운로드/삭제 키.")
    name: str = Field(description="원본 파일명 (저장된 디스크 파일명과 다를 수 있음).")
    size: int = Field(ge=0, description="바이트.")
    mime: str = Field(default="application/octet-stream")
    item_id: str | None = Field(
        default=None,
        description="연결된 체크리스트 항목 id. 매핑 시 해당 항목 status를 ready로 자동 승격.",
    )
    storage_path: str = Field(description="서버 로컬 저장 경로.")
    uploaded_at: str
    sha256: str | None = None


class UploadResponse(BaseModel):
    notice_no: str
    uploaded: UploadedDocument


class UploadListResponse(BaseModel):
    notice_no: str
    items: list[UploadedDocument]


class ExportRecord(BaseModel):
    kind: ExportKind
    draft_id: str = Field(description="원본 draft 식별자 (예: technical_compliance).")
    output_path: str
    mime: str
    generated_at: str
    notes: str | None = None


class ExportResponse(BaseModel):
    notice_no: str
    export: ExportRecord


# M12 — KJEBI 메일 paste-UI 추출
from api.llm.mail_schemas import KjebiMailExtraction  # noqa: E402


class MailExtractRequest(BaseModel):
    raw_text: str = Field(min_length=1, description="KJEBI 알림메일 본문 (사람이 paste).")
    source: str = Field(default="KJEBI")


class MailExtractResponse(BaseModel):
    extracted: KjebiMailExtraction
    upserted: NoticeRecord | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    errors: list[str] = Field(default_factory=list)


# M13 — G2B 라이브 검색 (등록 전 공고 존재 확인)


class NoticeSearchRequest(BaseModel):
    keyword: str = Field(min_length=1, description="공고명 검색 키워드 (G2B bidNtceNm 필터).")
    start_date: datetime | None = Field(
        default=None,
        description="시작일 (날짜만 사용). 미입력 시 오늘-30일.",
    )
    end_date: datetime | None = Field(
        default=None,
        description="종료일 (날짜만 사용). 미입력 시 오늘+30일.",
    )
    page: int = Field(default=1, ge=1, description="1부터 시작하는 페이지 번호.")
    page_size: int = Field(
        default=50,
        ge=1,
        le=200,
        description="페이지당 항목 수 (기본 50, 최대 200).",
    )


class NoticeSearchItem(BaseModel):
    notice_no: str = Field(description="autojebi 합성 PK: {bid_no}-{bid_seq}.")
    title: str
    source: str = "G2B"
    org_name: str | None = None
    base_price: int | None = None
    open_date: datetime | None = None
    close_date: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict, description="G2B 원본 응답 - upsert 시 그대로 전달.")
    already_exists: bool = Field(
        default=False,
        description="동일 source/notice_no가 DB(bid_pipeline)에 이미 존재하는지.",
    )


class NoticeSearchResponse(BaseModel):
    items: list[NoticeSearchItem]
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 0
