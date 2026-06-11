"""M3 그레이딩 결과 스키마.

abb-bid-pipeline의 app/grading/schemas.py에서 이식. QualificationInfo는 제외
(M3는 G2B 라이브 자격 API 호출 안 함 — M4 이후로 이연).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    """세 축 점수 분해 + 가중합."""

    spec: float = Field(description="사양 매칭 점수 0~1")
    qualification: float = Field(description="자격 점수 0~1")
    price: float = Field(description="예가 적정성 점수 0~1")
    weights: dict[str, float] = Field(description="가중치 dict (spec/qualification/price)")
    total: float = Field(description="가중합 0~1 (hard_gate 시 0)")


class FitSummary(BaseModel):
    """Claude가 한 줄로 적은 적합 사유."""

    reason: str = Field(description="공고가 ABB에 적합한 이유 (1~2 문장, 한국어 존대)")
    recommended_sku_id: str | None = Field(None, description="Top1 매칭 SKU ID")
    risk_note: str | None = Field(
        None,
        description="자격·예가에 결격 사유 있을 때만 한 줄",
    )


class QualificationInfo(BaseModel):
    """G2B LicenseLimit + PrtcptPsblRgn 두 엔드포인트의 통합 결과 (M5 부활)."""

    bid_no: str
    bid_seq: str
    # 참가가능지역명 목록. 비어 있으면 지역 제한 없음.
    regions: list[str] = Field(default_factory=list)
    # 면허제한명 목록. 비어 있으면 면허 제한 없음.
    licenses: list[str] = Field(default_factory=list)
    # 면허별 허용업종 목록 (참고용).
    permitted_industries: list[str] = Field(default_factory=list)
    # 호출 실패 시 메시지 — qualification.py에서 raw_json 휴리스틱으로 폴백.
    error: str | None = None
