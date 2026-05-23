from pydantic import BaseModel, Field


class BidSpecs(BaseModel):
    공고명: str = ""
    발주기관: str = ""
    추정가격: str = ""
    납기: str = ""
    입찰마감: str = ""
    공사_용역_유형: str = ""
    주요_기술요건: list[str] = []
    필수_자격_면허: list[str] = []
    현장_위치: str = ""


class BidSummaryOutput(BaseModel):
    summary: str
    specs: BidSpecs
    relevance_note: str = ""


# ============================================================================
# Phase 1 — 공급-쪽 데이터시트 추출 스키마 (Catalog 온톨로지 매핑 대상)
# ============================================================================


class CertificationSpec(BaseModel):
    """SKU 가 보유한 인증 1건."""
    name: str = Field(description="인증 이름 (e.g., 'KEPIC-EN', 'KS C IEC 60068', 'UL 1741')")
    issuer: str = Field(description="발급 기관 (e.g., 'KEPIC', 'KS', 'UL')")
    valid_until: str | None = Field(
        default=None,
        description="만료일 ISO date (YYYY-MM-DD). 데이터시트에 없으면 null.",
    )


class ProductSpecOutput(BaseModel):
    """공급사 데이터시트에서 추출된 SKU 1건의 사양.

    필드명은 ontology cat: 속성과 1:1 매핑된다 (`brand` → cat:hasBrand 등).
    LLM 이 모르는 필드는 null/빈값으로 둘 것 — fabrication 금지.
    """
    model_config = {"protected_namespaces": ()}

    sku_id: str = Field(description="고유 SKU 식별자 (제조사 모델번호 기반, 공백/특수문자 제거)")
    brand: str = Field(description="브랜드명 (e.g., 'ABB', 'Infineon', 'Mitsubishi', 'Plexim')")
    category: str = Field(
        description=(
            "카테고리 슬러그 (e.g., 'igbt-module', 'sic-mosfet', 'transformer', "
            "'inverter', 'simulation-sw', 'protection-relay'). 모르면 빈 문자열."
        )
    )
    model_number: str = Field(description="제조사 모델 번호 (e.g., '5SNA 1200E330100')")
    voltage_v: float | None = Field(default=None, description="정격 전압 V (DC 또는 RMS AC)")
    current_a: float | None = Field(default=None, description="정격 전류 A")
    power_w: float | None = Field(default=None, description="정격 전력 W")
    switching_freq_hz: float | None = Field(default=None, description="스위칭 주파수 Hz")
    certifications: list[CertificationSpec] = Field(
        default_factory=list,
        description="데이터시트에 언급된 보유 인증/규격 (없으면 빈 리스트)",
    )
    datasheet_excerpt: str = Field(
        default="",
        description="요약/검수용 발췌 (200자 이내, 핵심 사양 문단)",
    )
