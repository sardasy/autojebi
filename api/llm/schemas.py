"""전기 사양 추출 결과 스키마.

abb-bid-pipeline의 app/llm/schemas.py에서 무변경 이식.
ElecSpec은 Claude tool-use의 input_schema 원천이자 분석 결과 영속화 형식이다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ElecSpec(BaseModel):
    """Claude API가 반환하는 전기적 사양 구조체."""

    product_category: str | None = Field(
        None,
        description="제품군 (예: 변압기, 차단기, 인버터, UPS, 모터드라이브, 배전반, IGBT 모듈)",
    )
    quantity: int | None = Field(None, description="수량 (단위: 대/식/조)")

    # 전압 / 전류 / 용량
    rated_voltage_kv: float | None = Field(None, description="정격전압 (kV 단위, 예: 22.9, 0.38, 6.6)")
    rated_current_a: float | None = Field(None, description="정격전류 (A 단위)")
    rated_power_kva: float | None = Field(None, description="정격용량 (kVA 단위, 변압기/UPS 등)")
    rated_power_kw: float | None = Field(None, description="정격출력 (kW 단위, 인버터/드라이브 등)")
    frequency_hz: float | None = Field(None, description="주파수 (Hz, 보통 60)")

    # 구성
    phases: int | None = Field(None, description="상수 (1 또는 3)")
    breaking_capacity_ka: float | None = Field(
        None, description="차단용량 (kA, 차단기류에만 해당)"
    )

    # 설치 환경
    installation_type: str | None = Field(
        None, description="설치방식 (옥내 / 옥외 / 수배전반 내장 등)"
    )
    cooling_type: str | None = Field(
        None, description="냉각방식 (건식 / 유입 / 공랭 / 수랭 등)"
    )
    protection_class: str | None = Field(
        None, description="보호등급 (IP54, IP65 등 IEC 60529 기준)"
    )

    # 규격 및 기타
    standards: list[str] = Field(
        default_factory=list,
        description="적용규격 목록 (KS C 1234, IEC 60076, KEPCO 규격 등)",
    )
    notes: str | None = Field(
        None, description="위 항목에 해당하지 않는 중요 사양 (한 문장 이내)"
    )
