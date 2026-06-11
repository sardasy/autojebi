"""raw_json + 선택적 자격 API 결과 → 자격 점수 휴리스틱.

M5에서 qual_info 분기 복원. qual_info(LicenseLimit + PrtcptPsblRgn 통합 결과)가
있고 error가 없으면 region/license 분기 활성. 없거나 error 있으면 raw_json
휴리스틱으로 조용히 폴백.

G2B v1.2 명세 기반 raw_json 키:
- `cntrctCnclsMthdNm` (계약체결방법): "제한경쟁", "수의계약", "지명입찰" 등
- `bidQlfctRgstDt` (자격등록 일시)
- `cmmnSpldmdCorpRgnLmtYn` (공동수급체 지역제한 Y/N)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

from api.config import settings

if TYPE_CHECKING:
    from api.grading.schemas import QualificationInfo

log = logging.getLogger(__name__)


_CONTRACT_METHOD_KEY = "cntrctCnclsMthdNm"
_QLF_REG_DATE_KEY = "bidQlfctRgstDt"
_REGION_FLAG_KEY = "cmmnSpldmdCorpRgnLmtYn"

_KNOWN_RAW_KEYS = (_CONTRACT_METHOD_KEY, _QLF_REG_DATE_KEY, _REGION_FLAG_KEY)


def score_qualification(
    raw_json: str | None,
    qual_info: QualificationInfo | None = None,
) -> tuple[float, list[str]]:
    """raw_json + 선택적 qual_info를 자격 휴리스틱으로 평가.

    - qual_info가 있고 error가 없으면 region/license 분기 활성 (가장 강한 신호).
      region mismatch 시 0.0 (hard gate). license 있으면 -0.15.
    - qual_info.error 또는 None이면 raw_json 휴리스틱으로 폴백 (조용한 폴백).

    반환: (점수 0~1, 사유 메모 리스트).
    """
    notes: list[str] = []
    score = 1.0
    have_signal = False

    # ── 1) qual_info가 있고 error 없으면 region/license 분기 (가장 강한 신호)
    if qual_info is not None:
        if qual_info.error:
            notes.append(f"자격 API 호출 실패({qual_info.error[:80]}) → raw_json 휴리스틱으로 폴백")
        else:
            have_signal = True
            score, region_notes = _apply_region_rule(qual_info.regions, score)
            notes.extend(region_notes)
            if score == 0.0:
                return 0.0, notes

            if qual_info.licenses:
                score -= 0.15
                notes.append(
                    f"면허 제한 {len(qual_info.licenses)}건: "
                    + ", ".join(qual_info.licenses[:3])
                    + (" …" if len(qual_info.licenses) > 3 else "")
                    + " (-0.15)"
                )

    # ── 2) raw_json 휴리스틱 (qual_info 없거나 error 있을 때 fallback,
    #       또는 qual_info와 보조 신호로 함께 사용)
    if raw_json:
        try:
            raw = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        except (json.JSONDecodeError, TypeError):
            raw = None
            notes.append("raw_json 파싱 실패")
        else:
            if isinstance(raw, dict) and any(k in raw for k in _KNOWN_RAW_KEYS):
                have_signal = True

                cntrct = str(raw.get(_CONTRACT_METHOD_KEY, "") or "")
                if "수의" in cntrct or "지명" in cntrct:
                    score -= 0.5
                    notes.append(f"계약방법 '{cntrct}' — 지명 명단 확인 필요 (-0.5)")
                elif cntrct:
                    notes.append(f"계약방법 '{cntrct}'")

                qlf_close = raw.get(_QLF_REG_DATE_KEY)
                if qlf_close and _is_past(str(qlf_close)):
                    score -= 0.3
                    notes.append(f"자격등록 마감 '{qlf_close}' (-0.3)")

                if str(raw.get(_REGION_FLAG_KEY, "") or "").upper() == "Y":
                    notes.append("공동수급체 지역제한 표기")
            elif isinstance(raw, dict):
                log.warning("[qualification] raw_json에 알려진 자격 키 없음 — 명세 변경 가능성")
                if not have_signal:
                    notes.append("raw_json에 자격 키 없음 (명세 변경 의심)")

    score = max(0.0, min(1.0, score))

    if not have_signal:
        return 0.5, notes + ["자격 신호 없음 → 중립 0.5"]
    if not notes:
        notes.append("결격 사유 없음")
    return score, notes


def _apply_region_rule(regions: list[str], current: float) -> tuple[float, list[str]]:
    """참가가능지역 목록을 ABB 등록 지역과 매칭.

    - regions 비어있으면 지역 제한 없음 → 통과 + 노트.
    - "전국" in ABB 등록 → 통과 + 노트.
    - 공고 region 중 ABB 등록 region 부분문자열 포함 1개라도 있으면 통과 + 노트.
    - 아무것도 매치 안되면 0.0 (hard gate).
    """
    if not regions:
        return current, ["지역 제한 없음"]

    registered = settings.abb_region_list
    if "전국" in registered:
        return current, [f"지역 제한 ({', '.join(regions[:3])}…) — ABB 전국 등록"]

    for r in regions:
        if any(reg in r for reg in registered):
            return current, [f"참가가능지역 '{r}' ∈ ABB 등록"]
    return 0.0, [
        f"참가가능지역 {regions[:3]} ∉ ABB 등록 {registered} → 0.0 (hard gate)"
    ]


def _is_past(raw: str) -> bool:
    s = raw.strip()
    today = date.today()
    try:
        if "-" in s:
            dt = datetime.fromisoformat(s.split("+")[0].rstrip("Z").replace(" ", "T", 1))
            return dt.date() < today
        digits = "".join(ch for ch in s if ch.isdigit())[:8]
        if len(digits) < 8:
            return False
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8])) < today
    except (ValueError, IndexError):
        return False
