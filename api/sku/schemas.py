"""ABB SKU 카탈로그 및 매칭 결과 스키마.

abb-bid-pipeline의 app/sku/schemas.py에서 무변경 이식.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AbbSku(BaseModel):
    """ABB 제품 카탈로그 단일 항목."""

    sku_id: str = Field(description="ABB 내부 제품 코드")
    name: str = Field(description="제품명")
    category: str = Field(description="제품군 (변압기/차단기/드라이브/UPS/배전반 등)")
    description: str = Field(description="제품 설명 (임베딩 기반 검색 대상)")

    voltage_kv: float | None = None
    current_a: float | None = None
    power_kva: float | None = None
    power_kw: float | None = None
    phases: int | None = None
    cooling_type: str | None = None
    installation_type: str | None = None

    tags: list[str] = Field(default_factory=list)
    datasheet_url: str | None = None


class SkuMatch(BaseModel):
    score: float = Field(description="벡터 유사도 점수 (0~1, 높을수록 유사)")
    sku: AbbSku
