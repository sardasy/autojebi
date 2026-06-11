"""score_qualification에 qual_info 인자 전달 시 region/license 분기 검증 (M5)."""

from __future__ import annotations

import json

import pytest

from api.config import settings
from api.grading.qualification import score_qualification
from api.grading.schemas import QualificationInfo


@pytest.fixture(autouse=True)
def _restore_regions(monkeypatch):
    """기본 ABB 등록지역으로 복원 (다른 테스트 영향 차단)."""
    monkeypatch.setattr(settings, "abb_registered_regions", "서울,경기,전국")


def _qi(*, regions=None, licenses=None, error=None) -> QualificationInfo:
    return QualificationInfo(
        bid_no="X",
        bid_seq="00",
        regions=regions or [],
        licenses=licenses or [],
        error=error,
    )


class TestRegionRule:
    def test_no_region_restriction_passes(self):
        s, notes = score_qualification(None, _qi(regions=[]))
        assert s == 1.0
        assert any("지역 제한 없음" in n for n in notes)

    def test_jeonguk_in_registered_bypasses(self, monkeypatch):
        monkeypatch.setattr(settings, "abb_registered_regions", "서울,전국")
        s, notes = score_qualification(None, _qi(regions=["부산광역시"]))
        assert s == 1.0
        assert any("전국 등록" in n for n in notes)

    def test_region_match_passes(self, monkeypatch):
        monkeypatch.setattr(settings, "abb_registered_regions", "서울,경기")
        s, notes = score_qualification(None, _qi(regions=["서울특별시"]))
        assert s == 1.0
        assert any("∈ ABB 등록" in n for n in notes)

    def test_region_mismatch_hard_gate(self, monkeypatch):
        monkeypatch.setattr(settings, "abb_registered_regions", "서울,경기")
        s, notes = score_qualification(None, _qi(regions=["부산광역시"]))
        assert s == 0.0
        assert any("hard gate" in n for n in notes)


class TestLicensePenalty:
    def test_one_license_minus_015(self):
        s, notes = score_qualification(None, _qi(regions=[], licenses=["전기공사업/3001"]))
        assert s == pytest.approx(0.85, abs=1e-6)
        assert any("면허 제한" in n for n in notes)

    def test_multiple_licenses_truncated_in_note(self):
        s, notes = score_qualification(
            None, _qi(regions=[], licenses=["A", "B", "C", "D", "E"])
        )
        # 1번만 감점 (-0.15)
        assert s == pytest.approx(0.85, abs=1e-6)
        assert any("…" in n for n in notes)


class TestFallback:
    def test_qual_info_error_falls_back_to_raw_json(self):
        raw = json.dumps({"cntrctCnclsMthdNm": "제한경쟁"})
        qi = _qi(error="API down")
        s, notes = score_qualification(raw, qi)
        # raw_json 분기로 폴백 — 제한경쟁은 노트만, 감점 없음
        assert s == 1.0
        assert any("자격 API 호출 실패" in n for n in notes)
        assert any("제한경쟁" in n for n in notes)

    def test_qual_info_none_uses_raw_only(self):
        raw = json.dumps({"cntrctCnclsMthdNm": "수의계약"})
        s, _ = score_qualification(raw, None)
        # qual_info 없으면 raw_json 휴리스틱만 — 수의계약 -0.5
        assert s == pytest.approx(0.5, abs=1e-6)
