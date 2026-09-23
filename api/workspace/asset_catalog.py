"""Existing company-file categories: labels and roles, never compliance rules."""

import hashlib
import json
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict

AssetCategory = Literal["business_registration", "corporate_register", "credit_rating",
                        "sme_certificate", "insurance_payment", "seal_certificate", "other_evidence",
                        "previous_proposal", "product_catalogue"]
AssetRole = Literal["company_evidence", "company_reference", "product_evidence"]


class AssetCategoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: AssetCategory
    label: str
    role: AssetRole


_RECORDS = (
    AssetCategoryRecord(code="business_registration", label="사업자등록증", role="company_evidence"),
    AssetCategoryRecord(code="corporate_register", label="법인등기부등본", role="company_evidence"),
    AssetCategoryRecord(code="credit_rating", label="신용평가서", role="company_evidence"),
    AssetCategoryRecord(code="sme_certificate", label="중소기업확인서", role="company_evidence"),
    AssetCategoryRecord(code="insurance_payment", label="4대보험 완납증명서", role="company_evidence"),
    AssetCategoryRecord(code="seal_certificate", label="인감증명서", role="company_evidence"),
    AssetCategoryRecord(code="other_evidence", label="기타 증빙", role="company_evidence"),
    AssetCategoryRecord(code="previous_proposal", label="기존 제안서 · 참고용", role="company_reference"),
    AssetCategoryRecord(code="product_catalogue", label="제품 자료", role="product_evidence"),
)
CATEGORIES = MappingProxyType({item.code: item for item in _RECORDS})


class AssetCategoryCatalog(BaseModel):
    version: str
    sha256: str
    items: list[AssetCategoryRecord]


def category_catalog() -> AssetCategoryCatalog:
    payload = [record.model_dump() for record in _RECORDS]
    checksum = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
    return AssetCategoryCatalog(version="company-asset-categories-v1", sha256=checksum,
                                items=list(_RECORDS))


def category_role(code: str) -> str:
    # A malformed or unsupported historical category must not gain an evidence
    # role through a permissive fallback. Original files stay accessible.
    record = CATEGORIES.get(code)
    return record.role if record else "unknown"
