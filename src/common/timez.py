"""Timezone helpers.

DB columns are TIMESTAMP WITH TIME ZONE; defaults and parsed inputs must be
timezone-aware. KST is the source-of-truth zone for Korean public APIs.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = timezone.utc


def utcnow() -> datetime:
    """Aware UTC `now()`. Use as model default and for time-window queries."""
    return datetime.now(UTC)


def kst_to_utc(naive_kst: datetime) -> datetime:
    """Treat a naive datetime parsed from a KST-sourced field as KST, return UTC."""
    return naive_kst.replace(tzinfo=KST).astimezone(UTC)
