from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DocumentCategory = Literal[
    "proposal",
    "report",
    "certificate",
    "product",
    "company",
    "performance",
    "other",
]
IndexingStatus = Literal["pending", "indexed", "failed"]
RequirementType = Literal[
    "company_overview",
    "similar_experience",
    "technical_strength",
    "execution_plan",
    "maintenance",
    "quality",
    "security",
    "qualification",
    "documents",
    "other",
]
FactCheckStatus = Literal["pending", "pass", "warning", "reject"]


class DocumentChunkCreate(BaseModel):
    chunk_index: int = Field(ge=0)
    page_number: int | None = None
    heading: str | None = None
    content: str = Field(min_length=1)
    chunk_metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentChunkRecord(DocumentChunkCreate):
    id: str
    document_id: str
    token_count: int = 0


class ProposalDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    file_name: str | None = None
    file_path: str | None = None
    document_type: str | None = None
    category: DocumentCategory = "proposal"
    project_name: str | None = None
    customer_name: str | None = None
    checksum: str | None = None
    document_metadata: dict[str, Any] = Field(default_factory=dict)
    chunks: list[DocumentChunkCreate] = Field(default_factory=list)


class ProposalDocumentRecord(ProposalDocumentCreate):
    id: str
    indexing_status: IndexingStatus = "pending"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectPerformanceCreate(BaseModel):
    project_name: str = Field(min_length=1, max_length=500)
    customer_name: str | None = None
    contract_date: date | None = None
    completion_date: date | None = None
    contract_amount: float | None = None
    project_type: str | None = None
    technologies: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    description: str | None = None
    evidence_document_id: str | None = None
    verified: bool = False


class ProjectPerformanceRecord(ProjectPerformanceCreate):
    id: str


class NoticeRequirementRecord(BaseModel):
    id: str
    notice_no: str
    section: str
    requirement_type: RequirementType
    requirement_text: str
    mandatory: bool = True
    evaluation_score: float | None = None
    source_page: int | None = None
    extracted_data: dict[str, Any] = Field(default_factory=dict)


class RequirementEvidenceRecord(BaseModel):
    id: str
    requirement_id: str
    document_id: str | None = None
    chunk_id: str | None = None
    performance_id: str | None = None
    evidence_type: str
    relevance_score: float = 0.0
    confidence_score: float = 0.0
    quoted_text: str
    reasoning_summary: str | None = None
    approved: bool = False


class ProposalSectionRecord(BaseModel):
    id: str
    notice_no: str
    template_key: str = "proposal"
    section_key: str
    section_title: str
    generated_content: str
    generation_status: str = "draft"
    evidence_ids: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    fact_check_status: FactCheckStatus = "pending"
    fact_check_notes: list[dict[str, Any]] = Field(default_factory=list)
    human_approved: bool = False
    version: int = 1


class ProposalAnalyzeResponse(BaseModel):
    notice_no: str
    requirements: list[NoticeRequirementRecord]


class ProposalRetrieveResponse(BaseModel):
    notice_no: str
    evidences: list[RequirementEvidenceRecord]


class ProposalGenerateResponse(BaseModel):
    notice_no: str
    sections: list[ProposalSectionRecord]


class ProposalVerifyResponse(BaseModel):
    notice_no: str
    sections: list[ProposalSectionRecord]
    status: FactCheckStatus


class ProposalCoverageItem(BaseModel):
    requirement_id: str
    requirement_type: RequirementType
    requirement_text: str
    mandatory: bool
    evidence_count: int
    status: Literal["ready", "partial", "missing"]


class ProposalCoverageResponse(BaseModel):
    notice_no: str
    readiness_score: int
    items: list[ProposalCoverageItem]
