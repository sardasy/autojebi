"""Grade 비즈니스 로직 — 라우터·스케줄러 공용 진입점.

M5에서 grade_notice 본문을 분리. HTTP 비종속이라 도메인 예외(GradeError)를
던지면, 라우터는 HTTPException으로 변환하고 스케줄러는 로그만 남기고 다음 건 진행.

G2B 자격 API 라이브 호출(fetch_qualifications)을 새로 추가 — 실패 시 raw_json
휴리스틱으로 조용히 폴백.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import Engine, select, update

from api.config import settings
from api.grading.qualification import score_qualification
from api.grading.schemas import QualificationInfo
from api.grading.scorer import combine, score_price, score_spec
from api.grading.summarizer import summarize_fit
from api.llm.schemas import ElecSpec
from api.models.notices import NoticeGradeResponse
from api.services import qual_cache
from api.services.slack_notifier import SlackNotifier
from api.sku.matcher import match_skus
from api.tables import bid_pipeline

log = logging.getLogger(__name__)

_GRADEABLE_STATUSES = {
    "analyzed",
    "form_filled",
    "notified",
    "digest_queued",
    "archived_low",
}


class GradeError(Exception):
    """grading_runner 공통 도메인 예외 베이스."""


class GradeNotFoundError(GradeError):
    def __init__(self, notice_no: str) -> None:
        self.notice_no = notice_no
        super().__init__(f"notice not found: {notice_no}")


class GradeInvalidStatusError(GradeError):
    def __init__(self, notice_no: str, current_status: str) -> None:
        self.notice_no = notice_no
        self.current_status = current_status
        super().__init__(
            f"grade는 analyzed 이후만 가능 (current={current_status})"
        )


def _make_sku_matcher_store():
    """Qdrant lazy import — 의존성 미설치 환경 보호."""
    from api.sku.qdrant_store import QdrantStore

    return QdrantStore()


def _g2b_detail_url(row) -> str | None:
    raw = row["raw"] or {}
    url = (raw.get("bidNtceDtlUrl") or raw.get("bidNtceUrl") or "").strip()
    return url or None


def fetch_qual_safe(bid_no: str | None, bid_seq: str | None) -> QualificationInfo | None:
    """bid_no/bid_seq 둘 다 있을 때 G2B 자격 API 호출.

    M6: 캐시 hit이면 즉시 반환, 미스시에만 asyncio.run으로 라이브 호출.
    실패해도 None 반환 — 호출자(grade_notice_impl)는 raw_json 휴리스틱으로 폴백.
    절대 raise 안함.
    """
    if not bid_no or not bid_seq:
        return None

    cached = qual_cache.get(bid_no, bid_seq)
    if cached is not None:
        return cached

    try:
        info = asyncio.run(_fetch_qual_async(bid_no, bid_seq))
    except Exception as exc:  # noqa: BLE001
        log.warning("[grade] fetch_qualifications 실패 %s-%s: %s", bid_no, bid_seq, exc)
        return None

    qual_cache.set(info)
    return info


async def _fetch_qual_async(bid_no: str, bid_seq: str) -> QualificationInfo:
    from api.collector.g2b_client import G2BClient

    async with G2BClient() as client:
        return await client.fetch_qualifications(bid_no, bid_seq)


def grade_notice_impl(
    engine: Engine,
    notice_no: str,
    *,
    alert: bool = True,
) -> NoticeGradeResponse:
    """ElecSpec → Qdrant → 3축 그레이딩 → DB 저장 + fit_score 동기화 + Slack 알림.

    status 변동 없음. grade는 analyzed 이후 어디서든 재호출 가능.
    HTTP 비종속 — 도메인 예외(GradeError 계열)만 던진다.
    """
    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise GradeNotFoundError(notice_no)
        if row["status"] not in _GRADEABLE_STATUSES:
            raise GradeInvalidStatusError(notice_no, row["status"])

        analysis_dict = row["analysis"] or {}
        elec_dict = analysis_dict.get("elec_spec") or {}
        try:
            spec = ElecSpec.model_validate(elec_dict)
        except (ValidationError, TypeError) as exc:
            log.debug("[grade] elec_spec 파싱 실패 %s — 빈 ElecSpec 폴백: %s", notice_no, exc)
            spec = ElecSpec()

        raw_json = json.dumps(row["raw"]) if row["raw"] else None

        # SKU 매칭 — Qdrant 실패 시 빈 매칭으로 폴백
        try:
            store = _make_sku_matcher_store()
            query, matches = match_skus(spec, limit=5, store=store)
        except Exception as exc:  # noqa: BLE001
            query = ""
            matches = []
            analysis_dict.setdefault("errors", []).append(
                {"stage": "grade.qdrant", "detail": str(exc)[:200]}
            )

        top = matches[0] if matches else None

        # M5: 자격 API 라이브 호출 (실패 시 None — raw_json 휴리스틱으로 폴백)
        qual_info = fetch_qual_safe(row.get("bid_no"), row.get("bid_seq"))

        spec_s = score_spec(top)
        qual_s, qual_notes = score_qualification(raw_json, qual_info=qual_info)
        price_s, price_note = score_price(spec, row["base_price"], raw_json)
        breakdown = combine(spec_s, qual_s, price_s)

        summary = summarize_fit(
            bid_title=row["title"] or "",
            spec=spec,
            top_matches=matches,
            breakdown=breakdown,
            qual_notes=qual_notes,
            price_note=price_note,
        )

        merged_analysis = dict(analysis_dict)
        merged_analysis["grade"] = {
            "breakdown": breakdown.model_dump(),
            "qual_notes": qual_notes,
            "qual_info": qual_info.model_dump() if qual_info else None,
            "price_note": price_note,
            "matches": [m.model_dump() for m in matches[:3]],
            "query": query,
        }

        top_sku_id = summary.recommended_sku_id or (top.sku.sku_id if top else None)
        top_sku_name = top.sku.name if top else None
        now = datetime.now(tz=UTC)

        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(
                score_spec=spec_s,
                score_qual=qual_s,
                score_price=price_s,
                score_total=breakdown.total,
                grade_reason=summary.reason,
                risk_note=summary.risk_note,
                top_sku=top_sku_id,
                top_sku_name=top_sku_name,
                sku_match_score=top.score if top else None,
                graded_at=now,
                fit_score=int(round(breakdown.total * 100)),
                analysis=merged_analysis,
            )
        )

        delivered = False
        if alert and breakdown.total >= settings.grade_alert_threshold:
            notifier = SlackNotifier()
            outcome = notifier.send_grade_alert(
                title=row["title"] or notice_no,
                breakdown=breakdown,
                reason=summary.reason,
                top_sku_name=top_sku_name,
                risk_note=summary.risk_note,
                detail_url=_g2b_detail_url(row),
            )
            delivered = outcome.delivered

        return NoticeGradeResponse(
            notice_no=notice_no,
            score_spec=spec_s,
            score_qual=qual_s,
            score_price=price_s,
            score_total=breakdown.total,
            top_sku=top_sku_id,
            top_sku_name=top_sku_name,
            grade_reason=summary.reason,
            risk_note=summary.risk_note,
            slack_delivered=delivered,
            status=row["status"],
        )
