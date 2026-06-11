"""qual_cache 단위 테스트 (M6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api.config import settings
from api.grading.schemas import QualificationInfo
from api.services import qual_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    qual_cache.clear()
    yield
    qual_cache.clear()


def _qi(bid_no="A", bid_seq="00", *, regions=None, error=None) -> QualificationInfo:
    return QualificationInfo(
        bid_no=bid_no,
        bid_seq=bid_seq,
        regions=regions or [],
        error=error,
    )


def test_miss_returns_none():
    assert qual_cache.get("A", "00") is None


def test_set_then_get_returns_entry():
    qual_cache.set(_qi("A", "00", regions=["서울"]))
    result = qual_cache.get("A", "00")
    assert result is not None
    assert result.regions == ["서울"]


def test_size_reflects_entries():
    assert qual_cache.size() == 0
    qual_cache.set(_qi("A", "00"))
    qual_cache.set(_qi("B", "01"))
    assert qual_cache.size() == 2


def test_clear_removes_all():
    qual_cache.set(_qi("A", "00"))
    qual_cache.set(_qi("B", "01"))
    qual_cache.clear()
    assert qual_cache.size() == 0
    assert qual_cache.get("A", "00") is None


def test_error_qual_info_not_cached():
    qual_cache.set(_qi("A", "00", error="API down"))
    assert qual_cache.get("A", "00") is None
    assert qual_cache.size() == 0


def test_disabled_setting_bypasses_get_and_set(monkeypatch):
    monkeypatch.setattr(settings, "qual_cache_enabled", False)
    qual_cache.set(_qi("A", "00", regions=["서울"]))
    assert qual_cache.size() == 0  # set 무시
    # set 우회 후에도 get은 항상 None
    monkeypatch.setattr(settings, "qual_cache_enabled", True)
    qual_cache.set(_qi("A", "00", regions=["서울"]))
    monkeypatch.setattr(settings, "qual_cache_enabled", False)
    assert qual_cache.get("A", "00") is None  # get 우회


def test_ttl_expiry_returns_none(monkeypatch):
    """TTL 만료 시 lazy 삭제 + None 반환."""
    monkeypatch.setattr(settings, "qual_cache_ttl_hours", 24)
    qual_cache.set(_qi("A", "00", regions=["서울"]))
    assert qual_cache.size() == 1

    # _now()를 25시간 뒤로 monkeypatch
    future = datetime.now(tz=UTC) + timedelta(hours=25)
    monkeypatch.setattr(qual_cache, "_now", lambda: future)

    assert qual_cache.get("A", "00") is None
    assert qual_cache.size() == 0  # lazy 삭제


def test_separate_keys_are_independent():
    qual_cache.set(_qi("A", "00", regions=["서울"]))
    qual_cache.set(_qi("A", "01", regions=["부산"]))
    assert qual_cache.get("A", "00").regions == ["서울"]
    assert qual_cache.get("A", "01").regions == ["부산"]
    assert qual_cache.get("A", "99") is None


def test_set_overwrites_existing_entry():
    qual_cache.set(_qi("A", "00", regions=["서울"]))
    qual_cache.set(_qi("A", "00", regions=["부산"]))
    assert qual_cache.get("A", "00").regions == ["부산"]
    assert qual_cache.size() == 1


def test_thread_safe_basic(monkeypatch):
    """간단 스레드 동시성 — 락 없이 dict가 깨지지 않는지."""
    import threading

    def writer(start: int):
        for i in range(start, start + 50):
            qual_cache.set(_qi(f"T{i}", "00", regions=[f"region-{i}"]))

    threads = [threading.Thread(target=writer, args=(s,)) for s in (0, 100, 200, 300)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert qual_cache.size() == 200
