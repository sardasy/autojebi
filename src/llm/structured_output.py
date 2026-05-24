from __future__ import annotations
import re
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# 가격/비율 normalizer (LLM 또는 backfill 의 원본이 string 일 수 있음)
# ---------------------------------------------------------------------------
_NUMBER_PUNCT_RE = re.compile(r"[원,\s%₩]")


def _to_optional_float(v):
    """공통 가격 parser. None/빈문자열 → None, '850,000,000원' → 850000000.0."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    s = _NUMBER_PUNCT_RE.sub("", s)
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_nakchal_rate(v):
    """낙찰하한율 normalize.

    - None / 빈값 → None
    - 0 < x <= 1 → 그대로 (이미 소수)
    - 1 < x <= 100 → /100 (퍼센트 표기를 소수로)
    - 그 외 → None (룰엔진에 전달 불가)
    """
    f = _to_optional_float(v)
    if f is None:
        return None
    if 0 < f <= 1:
        return f
    if 1 < f <= 100:
        return round(f / 100.0, 6)
    return None


_TENDER_TYPES = ("일반경쟁", "제한경쟁", "협상에의한계약", "수의계약", "MAS", "지명경쟁", "unknown")
_EVAL_METHODS = ("적격심사", "종합평가", "최저가", "협상", "2단계경쟁", "unknown")
TenderType = Literal[
    "일반경쟁", "제한경쟁", "협상에의한계약", "수의계약", "MAS", "지명경쟁", "unknown",
]
EvaluationMethod = Literal[
    "적격심사", "종합평가", "최저가", "협상", "2단계경쟁", "unknown",
]


class BidSpecs(BaseModel):
    """LLM 이 추출하는 공고 핵심 사양.

    원본 데이터가 string/숫자/None 어느 쪽으로 와도 동일한 형태로 정규화한다.
    추가 필드는 룰엔진(src/bidding/) 입력으로 사용.
    """

    # --- 기존 필드 (정규화 강화) ---
    공고명: str = ""
    발주기관: str = ""
    추정가격: Optional[float] = None  # 사업 규모 명목값 (KRW)
    납기: Optional[str] = None
    입찰마감: Optional[str] = None
    공사_용역_유형: Optional[str] = None
    주요_기술요건: list[str] = Field(default_factory=list)
    필수_자격_면허: list[str] = Field(default_factory=list)
    현장_위치: Optional[str] = None

    # --- 추가 필드 (룰엔진 입력) ---
    기초금액: Optional[float] = Field(
        default=None,
        description="발주처 산정 기초금액 (KRW). 추정가격과 별개로 둘 다 있으면 둘 다 채움.",
    )
    낙찰하한율: Optional[float] = Field(
        default=None,
        description="0~1 사이 소수. 87.745% / 0.87745 / 87.745 모두 0.87745 로 정규화.",
    )
    입찰방식: Optional[TenderType] = "unknown"
    낙찰자선정방식: Optional[EvaluationMethod] = "unknown"
    직접생산증명요구: bool = False
    위임장허용: bool = False
    조달청물품분류번호: Optional[str] = None
    적격심사_배점: Optional[dict[str, float]] = Field(
        default=None,
        description='예: {"납품실적":30, "경영상태":30, "기술능력":10, "신인도":0, "입찰가격":30}',
    )

    # --- validator ---
    @field_validator("추정가격", "기초금액", mode="before")
    @classmethod
    def _parse_price(cls, v):
        return _to_optional_float(v)

    @field_validator("낙찰하한율", mode="before")
    @classmethod
    def _parse_rate(cls, v):
        return _normalize_nakchal_rate(v)

    @field_validator("납기", "입찰마감", "공사_용역_유형", "현장_위치", "조달청물품분류번호",
                     mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("입찰방식", mode="before")
    @classmethod
    def _coerce_tender_type(cls, v):
        if v is None:
            return "unknown"
        s = str(v).strip()
        return s if s in _TENDER_TYPES else "unknown"

    @field_validator("낙찰자선정방식", mode="before")
    @classmethod
    def _coerce_eval_method(cls, v):
        if v is None:
            return "unknown"
        s = str(v).strip()
        return s if s in _EVAL_METHODS else "unknown"


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
