"""공고 유입 — KJEBI 메일 추출, G2B 라이브 검색."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.db import require_engine
from api.models.notices import (
    MailExtractRequest,
    MailExtractResponse,
    NoticeRecord,
    NoticeSearchRequest,
    NoticeSearchResponse,
    NoticeUpsertRequest,
)
from api.services.mail_extractor import extract_notice_from_mail

from .crud import upsert_notice

router = APIRouter()


@router.post("/extract-from-mail", response_model=MailExtractResponse)
def extract_from_mail(payload: MailExtractRequest) -> MailExtractResponse:
    """M12 — KJEBI 알림메일 paste → Claude tool-use 추출 → notice_no 있으면 upsert.

    실 메일 샘플이 확보되기 전까지의 1차 운영 경로. n8n 자동화는 M12.5에서 본격 구현.
    notice_no 추출 실패 시 upserted=null로 반환 — 호출자(프론트)가 사용자에게 경고.
    """
    result = extract_notice_from_mail(payload.raw_text)
    upserted: NoticeRecord | None = None

    if result.extracted.notice_no:
        upsert_payload = NoticeUpsertRequest(
            notice_no=result.extracted.notice_no,
            title=result.extracted.title,
            source=payload.source,
            raw={
                "kjebi_mail": payload.raw_text,
                "extracted": result.extracted.model_dump(),
            },
        )
        upserted = upsert_notice(upsert_payload)

    return MailExtractResponse(
        extracted=result.extracted,
        upserted=upserted,
        confidence=result.confidence,
        errors=result.errors,
    )


@router.post("/search", response_model=NoticeSearchResponse)
def search_notices_endpoint(payload: NoticeSearchRequest) -> NoticeSearchResponse:
    """M13 — G2B 라이브 검색. DB write 없음.

    페이지네이션: payload.page (>=1), payload.page_size (1..200, 기본 50).
    응답은 슬라이스된 items + 전체 total/total_pages를 함께 반환한다.
    page > total_pages인 경우도 정상 응답 (빈 items + 정확한 meta).

    422 — 빈 키워드 / start > end / 365일 초과 / page<1 / page_size 범위 위반.
    502 — G2B API 호출 실패 (네트워크/HTTP/파싱).
    """
    from datetime import date as _date
    from datetime import timedelta as _td

    from api.collector.pipeline import search_notices

    keyword = (payload.keyword or "").strip()
    if not keyword:
        raise HTTPException(status_code=422, detail="keyword must not be empty")

    today = _date.today()
    start = payload.start_date.date() if payload.start_date else (today - _td(days=30))
    end = payload.end_date.date() if payload.end_date else (today + _td(days=30))

    if start > end:
        raise HTTPException(
            status_code=422, detail=f"start_date {start} must not be after end_date {end}"
        )
    if (end - start).days > 365:
        raise HTTPException(
            status_code=422, detail="search range must not exceed 365 days"
        )

    engine = require_engine()
    try:
        return search_notices(
            engine=engine,
            start=start,
            end=end,
            keyword=keyword,
            page=payload.page,
            page_size=payload.page_size,
        )
    except HTTPException:
        raise
    except Exception as exc:
        # G2B HTTP/네트워크/파싱 실패 → 외부 의존성 장애로 분류
        raise HTTPException(status_code=502, detail=f"G2B search failed: {exc}")
