"""Request/response models for original notice form filling."""

from __future__ import annotations

from pydantic import Field, HttpUrl

from api.workspace.models import StrictModel, VersionRequest


class FormReference(StrictModel):
    document_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=12000)


class FormWebReference(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    quote: str = Field(min_length=1, max_length=12000)


class FormValue(StrictModel):
    field_id: str = Field(min_length=1, max_length=100)
    value: str = Field(default="", max_length=12000)
    reference: FormReference | None = None
    web_reference: FormWebReference | None = None


class FormFillingRequest(VersionRequest):
    document_id: str = Field(min_length=1, max_length=200)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=100)
    fields: list[FormValue] = Field(default_factory=list, max_length=200)
    note: str = Field(min_length=1, max_length=2000)


class FormReviewRequest(VersionRequest):
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved: bool
    source_checked: bool = False
    content_checked: bool = False
    layout_checked: bool = False
    note: str = Field(min_length=1, max_length=2000)


class FormReviewTarget(StrictModel):
    version: int
    output_sha256: str
    unfilled_count: int
    review_status: str
