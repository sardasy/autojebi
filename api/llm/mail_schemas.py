"""KJEBI 알림메일 paste → 공고 메타 추출 스키마 (M12).

Claude tool-use(`extract_notice_from_mail`)의 input_schema 원천이자
`POST /notices/extract-from-mail` 응답 페이로드의 일부.

확장 시 주의 — 필드 추가는 confidence 계산식([api/services/mail_extractor.py])과 함께 갱신.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class KjebiMailExtraction(BaseModel):
    """KJEBI 알림메일에서 추출한 공고 핵심 메타.

    모든 필드 optional — Claude는 명시된 값만 채운다. 추정 금지.
    `notice_no`가 없으면 upsert 불가 (PK 형식 `{bid_no}-{bid_seq}`).
    """

    notice_no: str | None = Field(
        None,
        description=(
            "공고번호. 형식 `{bid_no}-{bid_seq}` (예: R26BK01543282-000). "
            "메일 본문에 분리 표기되면 합쳐서 반환."
        ),
    )
    title: str | None = Field(None, description="공고 제목 한 줄.")
    org_name: str | None = Field(None, description="발주기관명 (예: 한국전력공사).")
    close_date: str | None = Field(
        None,
        description=(
            "입찰 마감 일시 ISO 8601 (KST 가정, 예: '2026-06-20T18:00:00+09:00'). "
            "메일에 시간 없으면 18:00:00 가정."
        ),
    )
    base_price: float | None = Field(
        None, description="예가/추정가 원 단위 (예: 50_000_000)."
    )
    bid_url: str | None = Field(
        None, description="G2B 원문 URL (https://www.g2b.go.kr/... 포함 시)."
    )
    summary: str | None = Field(None, description="공고 요지 한 문장 (한국어).")
