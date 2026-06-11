"""G2B 자격 API 응답 in-memory 캐시 (M6).

프로세스 로컬 dict + threading.Lock. TTL 만료 시 lazy 무효화.
fetch_qualifications가 error를 반환한 경우엔 캐싱하지 않음 — 일시 장애 후 즉시 재시도 가능.

운영 규모가 멀티워커/멀티레플리카로 커지면 DB 테이블 또는 Redis로 교체 (M8+).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from api.config import settings
from api.grading.schemas import QualificationInfo

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CacheEntry:
    qual_info: QualificationInfo
    expires_at: datetime


_CACHE: dict[tuple[str, str], _CacheEntry] = {}
_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(tz=UTC)


def get(bid_no: str, bid_seq: str) -> QualificationInfo | None:
    """캐시 hit + 미만료 시 QualificationInfo, 그 외 None.

    QUAL_CACHE_ENABLED=false면 항상 None.
    """
    if not settings.qual_cache_enabled:
        return None
    key = (bid_no, bid_seq)
    with _LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        if entry.expires_at <= _now():
            # 만료 — lazy 삭제
            _CACHE.pop(key, None)
            return None
    log.info("[qual_cache] hit %s-%s", bid_no, bid_seq)
    return entry.qual_info


def set(qual_info: QualificationInfo) -> None:
    """성공한 QualificationInfo만 저장 — error 있으면 캐싱 건너뜀."""
    if not settings.qual_cache_enabled:
        return
    if qual_info.error:
        return
    key = (qual_info.bid_no, qual_info.bid_seq)
    ttl = timedelta(hours=settings.qual_cache_ttl_hours)
    with _LOCK:
        _CACHE[key] = _CacheEntry(qual_info=qual_info, expires_at=_now() + ttl)
    log.info(
        "[qual_cache] store %s-%s (ttl=%dh)",
        qual_info.bid_no,
        qual_info.bid_seq,
        settings.qual_cache_ttl_hours,
    )


def clear() -> None:
    """테스트용 — 캐시 비움."""
    with _LOCK:
        _CACHE.clear()


def size() -> int:
    """테스트/디버그용 — 현재 캐시 entry 수."""
    with _LOCK:
        return len(_CACHE)


def cleanup_expired() -> int:
    """만료된 entry를 일괄 제거. 반환값은 제거 개수.

    스케줄러가 주기적으로 호출 — lazy 무효화만 의존하면 grade 호출이 없는
    notice key는 영원히 남아 메모리를 점유한다.
    """
    now = _now()
    with _LOCK:
        expired = [k for k, v in _CACHE.items() if v.expires_at <= now]
        for k in expired:
            _CACHE.pop(k, None)
    if expired:
        log.info("[qual_cache] cleanup removed %d expired entries", len(expired))
    return len(expired)
