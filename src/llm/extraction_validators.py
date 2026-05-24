"""정규식 추출기 + LLM 결과 교차검증.

LLM 단독 추출은 금액·날짜·분류번호에서 hallucination 위험이 크므로,
한국 공고문 정규 표기로부터 결정적으로 뽑을 수 있는 값은 regex 로 한 번 더 추출하고
LLM 값과 비교한다. 충돌 발생 시:
- critical (금액/낙찰하한율/마감일/분류번호): regex 값을 채택 + needs_human_review=True
- warning: LLM 값 유지 + 로그만

regex/LLM 둘 다 못 뽑은 필드는 그대로 None (둘 다 None 은 conflict 아님).
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any, Literal, Optional

from src.llm.structured_output import BidSpecs

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Korean amount → int
# ---------------------------------------------------------------------------

# Hanja → Hangul 정규화
_HANJA_NUM = {
    "壹": "일", "貳": "이", "參": "삼", "肆": "사", "伍": "오",
    "陸": "육", "柒": "칠", "捌": "팔", "玖": "구",
    "拾": "십", "佰": "백", "仟": "천",
    "萬": "만", "億": "억", "兆": "조",
    "一": "일", "二": "이", "三": "삼", "四": "사", "五": "오",
    "六": "육", "七": "칠", "八": "팔", "九": "구",
    "十": "십", "百": "백", "千": "천", "万": "만",
}
_DIGITS = {"영": 0, "공": 0, "일": 1, "이": 2, "삼": 3, "사": 4,
           "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_SMALL = {"십": 10, "백": 100, "천": 1000}
_BIG = {"만": 10**4, "억": 10**8, "조": 10**12}
_PREFIX_RE = re.compile(r"^(일금|금)\s*")
_SUFFIX_RE = re.compile(r"\s*(원정|원|정)$")


def korean_amount_to_int(text: str) -> int | None:
    """'일금 일억오천만원정' / '壹億伍仟萬' / '일억오천만' → 150000000.

    빈 문자열 / 파싱 불가 → None.
    """
    if not text:
        return None
    s = text.strip()
    s = _PREFIX_RE.sub("", s)
    s = _SUFFIX_RE.sub("", s)
    # 한자 → 한글 정규화
    s = "".join(_HANJA_NUM.get(c, c) for c in s)
    # 공백 / 콤마 제거
    s = re.sub(r"[\s,]", "", s)
    if not s:
        return None

    total = 0
    section = 0
    digit = 0
    for c in s:
        if c.isdigit():
            digit = digit * 10 + int(c)
        elif c in _DIGITS:
            digit = _DIGITS[c]
        elif c in _SMALL:
            if digit == 0:
                digit = 1
            section += digit * _SMALL[c]
            digit = 0
        elif c in _BIG:
            section += digit
            if section == 0:
                section = 1
            total += section * _BIG[c]
            section = 0
            digit = 0
        else:
            # 알 수 없는 문자 — 무시 (불완전한 정리)
            continue

    total += section + digit
    return total if total > 0 else None


# ---------------------------------------------------------------------------
# RegexExtractor
# ---------------------------------------------------------------------------

class RegexExtractor:
    """한국 공고문에서 결정적 필드를 정규식으로 추출."""

    # 가격 (숫자 콤마 표기)
    _PRICE_NUM_RE = re.compile(
        r"기초\s*[\(（]?\s*예비\s*[\)）]?\s*금액[\s:\-￦]*([0-9][\d,]*)\s*원?",
        re.IGNORECASE,
    )
    _PRICE_NUM_RE_ALT = re.compile(
        r"기초\s*금액[\s:\-￦]*([0-9][\d,]*)\s*원?",
        re.IGNORECASE,
    )
    # 한글/한자 금액 ("일금 ... 원정")
    _PRICE_KR_RE = re.compile(
        r"기초\s*금액[\s:\-￦]*(일금[^\n]*?원정?)",
        re.IGNORECASE,
    )
    _EST_PRICE_NUM_RE = re.compile(
        r"추정\s*가격[\s:\-￦]*([0-9][\d,]*)\s*원?",
        re.IGNORECASE,
    )

    # 낙찰하한율 (% 또는 소수)
    _NAKCHAL_RE = re.compile(
        r"낙찰\s*하한가?\s*율[\s:\-]*([0-9]+(?:\.[0-9]+)?)\s*%?",
        re.IGNORECASE,
    )

    # 마감일 — "2026-03-15 14:00" / "2026.03.15 14:00" / "2026년 3월 15일 14시" 등
    _DEADLINE_RE = re.compile(
        r"입찰\s*마감[일시\s\-:]*"
        r"([0-9]{4})[\.\-/년]\s*([0-9]{1,2})[\.\-/월]\s*([0-9]{1,2})[일\s]*"
        r"(?:([0-9]{1,2})[:시]\s*([0-9]{1,2})분?)?",
        re.IGNORECASE,
    )

    # 조달청 물품분류번호 (8자리)
    _CLASS_RE = re.compile(
        r"(?:조달청\s*)?물품\s*분류\s*번호[\s:\-]*([0-9]{8})",
        re.IGNORECASE,
    )

    # 입찰방식 / 낙찰자선정방식 키워드
    _TENDER_WORDS = {
        "일반경쟁": ["일반경쟁입찰", "일반경쟁"],
        "제한경쟁": ["제한경쟁입찰", "제한경쟁"],
        "협상에의한계약": ["협상에 의한 계약", "협상에의한계약"],
        "수의계약": ["수의계약"],
        "MAS": ["다수공급자계약", "MAS"],
        "지명경쟁": ["지명경쟁입찰", "지명경쟁"],
    }
    _EVAL_WORDS = {
        "적격심사": ["적격심사"],
        "종합평가": ["종합평가", "종합심사"],
        "최저가": ["최저가낙찰", "최저가"],
        "협상": ["협상에 의한 계약", "협상"],
        "2단계경쟁": ["2단계경쟁", "이단계경쟁"],
    }

    # 직접생산 / 위임장
    _DIRECT_MFG_RE = re.compile(
        r"직접\s*생산\s*(증명|확인)|직접\s*생산만",
    )
    _LOA_RE = re.compile(
        r"위임장|LoA|Letter\s+of\s+Authorization|대리점\s*위임",
        re.IGNORECASE,
    )

    # -------------------------------------------------------- public methods
    def extract_base_price(self, text: str) -> float | None:
        for pattern in (self._PRICE_NUM_RE, self._PRICE_NUM_RE_ALT):
            m = pattern.search(text)
            if m:
                try:
                    return float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
        m = self._PRICE_KR_RE.search(text)
        if m:
            v = korean_amount_to_int(m.group(1))
            if v:
                return float(v)
        return None

    def extract_estimated_price(self, text: str) -> float | None:
        m = self._EST_PRICE_NUM_RE.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                return None
        return None

    def extract_nakchal_rate(self, text: str) -> float | None:
        m = self._NAKCHAL_RE.search(text)
        if not m:
            return None
        try:
            v = float(m.group(1))
        except ValueError:
            return None
        if 0 < v <= 1:
            return v
        if 1 < v <= 100:
            return round(v / 100.0, 6)
        return None

    def extract_deadline(self, text: str) -> datetime | None:
        m = self._DEADLINE_RE.search(text)
        if not m:
            return None
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hh = int(m.group(4)) if m.group(4) else 0
            mi = int(m.group(5)) if m.group(5) else 0
            return datetime(y, mo, d, hh, mi)
        except (ValueError, TypeError):
            return None

    def extract_classification(self, text: str) -> str | None:
        m = self._CLASS_RE.search(text)
        return m.group(1) if m else None

    def extract_tender_type(self, text: str) -> str | None:
        for canonical, words in self._TENDER_WORDS.items():
            if any(w in text for w in words):
                return canonical
        return None

    def extract_evaluation_method(self, text: str) -> str | None:
        for canonical, words in self._EVAL_WORDS.items():
            if any(w in text for w in words):
                return canonical
        return None

    def extract_direct_mfg(self, text: str) -> bool:
        return bool(self._DIRECT_MFG_RE.search(text))

    def extract_loa_accepted(self, text: str) -> bool:
        return bool(self._LOA_RE.search(text))


# ---------------------------------------------------------------------------
# Dual extractor
# ---------------------------------------------------------------------------

Severity = Literal["critical", "warning"]


@dataclass
class ValidationConflict:
    field: str
    regex_value: Any
    llm_value: Any
    severity: Severity

    def to_dict(self) -> dict:
        return {**asdict(self), "regex_value": _to_jsonable(self.regex_value),
                "llm_value": _to_jsonable(self.llm_value)}


def _to_jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


# 금액 비교 임계
_PRICE_REL_TOL = 0.01       # 1%
_RATE_ABS_TOL = 0.001


class DualExtractor:
    """regex + LLM 결과 교차검증."""

    def __init__(self, regex: RegexExtractor | None = None):
        self.regex = regex or RegexExtractor()

    async def extract_with_validation(
        self,
        text: str,
        llm_gateway,  # LLMGateway 형식만 맞추면 됨 (avoid circular import)
        *,
        attachment_text: str = "",
    ) -> tuple[BidSpecs, list[ValidationConflict]]:
        # 비교 대상 텍스트: 본문 + 첨부 합본 (정규식은 풍부한 텍스트에서 더 잘 잡힘)
        full_text = "\n\n".join(filter(None, [text, attachment_text]))

        # 1) LLM 추출 (gateway 가 attachment_text 를 별도 받음)
        llm_out = await llm_gateway.summarize_bid(text, attachment_text=attachment_text)
        llm_specs = llm_out.specs if llm_out is not None else BidSpecs()

        # 2) regex 추출
        rex = self.regex
        re_base = rex.extract_base_price(full_text)
        re_est = rex.extract_estimated_price(full_text)
        re_rate = rex.extract_nakchal_rate(full_text)
        re_dl = rex.extract_deadline(full_text)
        re_cls = rex.extract_classification(full_text)
        re_tt = rex.extract_tender_type(full_text)
        re_em = rex.extract_evaluation_method(full_text)
        re_dmfg = rex.extract_direct_mfg(full_text)
        re_loa = rex.extract_loa_accepted(full_text)

        conflicts: list[ValidationConflict] = []
        merged = llm_specs.model_dump()

        # 가격 비교: 상대 오차
        for fld, re_v in (("기초금액", re_base), ("추정가격", re_est)):
            llm_v = merged.get(fld)
            if re_v is not None and llm_v is not None:
                if not _close_relative(re_v, llm_v, _PRICE_REL_TOL):
                    conflicts.append(ValidationConflict(fld, re_v, llm_v, "critical"))
                    merged[fld] = re_v  # regex 우선
            elif re_v is not None and llm_v is None:
                merged[fld] = re_v
            # 양쪽 None: skip

        # 낙찰하한율
        llm_rate = merged.get("낙찰하한율")
        if re_rate is not None and llm_rate is not None:
            if abs(re_rate - llm_rate) > _RATE_ABS_TOL:
                conflicts.append(ValidationConflict("낙찰하한율", re_rate, llm_rate, "critical"))
                merged["낙찰하한율"] = re_rate
        elif re_rate is not None and llm_rate is None:
            merged["낙찰하한율"] = re_rate

        # 마감일 (date 비교)
        llm_dl_str = merged.get("입찰마감")
        llm_dl = _parse_datetime_loose(llm_dl_str) if llm_dl_str else None
        if re_dl is not None and llm_dl is not None:
            if re_dl.date() != llm_dl.date():
                conflicts.append(ValidationConflict(
                    "입찰마감", re_dl.isoformat(), llm_dl_str, "critical",
                ))
                merged["입찰마감"] = re_dl.isoformat()
        elif re_dl is not None and llm_dl is None:
            merged["입찰마감"] = re_dl.isoformat()

        # 분류번호 (exact)
        llm_cls = merged.get("조달청물품분류번호")
        if re_cls is not None and llm_cls is not None:
            if re_cls != str(llm_cls):
                conflicts.append(ValidationConflict(
                    "조달청물품분류번호", re_cls, llm_cls, "critical",
                ))
                merged["조달청물품분류번호"] = re_cls
        elif re_cls is not None and llm_cls is None:
            merged["조달청물품분류번호"] = re_cls

        # 입찰방식 / 평가방식 — warning level (LLM 우선 유지, regex 가 다르면 로그)
        for fld, re_v in (("입찰방식", re_tt), ("낙찰자선정방식", re_em)):
            llm_v = merged.get(fld)
            if re_v and llm_v and llm_v not in ("unknown",) and re_v != llm_v:
                conflicts.append(ValidationConflict(fld, re_v, llm_v, "warning"))
            elif re_v and llm_v in (None, "unknown"):
                merged[fld] = re_v

        # 직접생산 / 위임장 — 우선순위: LLM=False, regex=True → regex
        for fld, re_v in (("직접생산증명요구", re_dmfg), ("위임장허용", re_loa)):
            llm_v = bool(merged.get(fld))
            if re_v and not llm_v:
                merged[fld] = True  # regex 가 명시적으로 발견했다면 채택

        final = BidSpecs.model_validate(merged)
        return final, conflicts


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _close_relative(a: float, b: float, tol: float) -> bool:
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom <= tol


_DATETIME_PATTERNS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M", "%Y.%m.%d %H:%M",
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%Y년 %m월 %d일 %H시 %M분", "%Y년 %m월 %d일 %H시",
    "%Y년 %m월 %d일",
]


def _parse_datetime_loose(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    for fmt in _DATETIME_PATTERNS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
