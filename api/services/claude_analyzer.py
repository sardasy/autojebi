"""M2 실가동 분석기.

기존 stub(키워드 매칭)에서 실제 Claude tool-use 호출로 교체. `AnalyzeResult`
데이터클래스와 `ClaudeAnalyzer.analyze_notice(notice_no, title, raw)` 시그니처는
보존 — router는 try/except 없이 호출하므로 본 메서드는 **절대 raise 금지**.

흐름:
  1) G2B raw의 첫 첨부 다운/추출 (LLM_ATTACHMENT_FETCH=true일 때만)
  2) extract_specs(...) → ElecSpec
  3) ElecSpec.product_category + title 키워드 → autojebi Category 매핑
  4) ElecSpec 완성도 + 카테고리 → fit_score (M2 임시 휴리스틱)

기존 JSON parsing 헬퍼(extract_first_json_object, safe_parse_json_object)는
tests/test_claude_json_parsing.py가 의존하므로 그대로 보존.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from api.config import settings
from api.llm.extractor import extract_specs_with_validation
from api.llm.schemas import ElecSpec
from api.services.attachments import fetch_first_attachment_text
from api.services.hwp_agent_client import HwpAgentClient

log = logging.getLogger(__name__)

Category = Literal["HIL", "SW", "IGBT", "SCR", "수동소자", "ABB장비", "혼합", "비관련"]


def extract_first_json_object(text: str) -> str | None:
    """
    AGENTS.md rule:
    - Strip code fences and parse only the first '{' .. last '}' slice.
    - Never raise; return None on failure.
    """
    if not text:
        return None

    cleaned = text.replace("```json", "").replace("```", "")
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return cleaned[start : end + 1]


def safe_parse_json_object(text: str) -> dict[str, Any]:
    snippet = extract_first_json_object(text)
    if not snippet:
        return {}
    try:
        value = json.loads(snippet)
        if isinstance(value, dict):
            return value
        return {}
    except Exception:
        return {}


@dataclass(frozen=True)
class AnalyzeResult:
    category: str
    fit_score: int
    analysis: dict[str, Any]


_G2B_SUMMARY_KEYS = (
    "bidNtceNm",
    "ntceInsttNm",
    "dminsttNm",
    "presmptPrce",
    "asignBdgtAmt",
    "bidNtceDt",
    "bidClseDt",
    "cntrctCnclsMthdNm",
    "bidMethdNm",
    "dtilPrdctClsfcNoNm",
    "prdctSpecNm",
)


def _summarize_raw_g2b(raw: dict[str, Any] | None) -> str | None:
    if not raw:
        return None
    lines: list[str] = []
    for key in _G2B_SUMMARY_KEYS:
        val = raw.get(key)
        if val:
            lines.append(f"{key}: {val}")
    return "\n".join(lines) if lines else None


_ABB_HARDWARE_KEYWORDS = ("변압기", "차단기", "ups", "인버터", "모터드라이브", "배전반")
_PASSIVE_KEYWORDS = (
    "퓨즈",
    "커패시터",
    "콘덴서",
    "부스바",
    "fuse",
    "capacitor",
    "busbar",
)


def map_elec_to_category(spec: ElecSpec, title: str | None) -> Category:
    """ElecSpec.product_category + title 키워드 → autojebi Category.

    HIL/PLECS는 ElecSpec 도메인 밖이므로 title 키워드로만 잡는다.
    """
    t = (title or "").lower()
    if "typhoon" in t or "hil" in t:
        return "HIL"
    if "plecs" in t:
        return "SW"

    pc = (spec.product_category or "").strip().lower()
    if not pc:
        return "비관련"
    if "igbt" in pc:
        return "IGBT"
    if "scr" in pc:
        return "SCR"
    if any(k in pc for k in _ABB_HARDWARE_KEYWORDS):
        return "ABB장비"
    if any(k in pc for k in _PASSIVE_KEYWORDS):
        return "수동소자"
    return "혼합"


def compute_fit_score(spec: ElecSpec, category: Category) -> int:
    """M2 임시 휴리스틱. M3 그레이딩 도입 시 score_total*100으로 대체."""
    if category == "비관련":
        return 0
    if category in ("HIL", "SW"):
        return 75  # 키워드 정확 매치 시 알림 가치 인정

    # 핵심 필드 완성도 (kva/kw는 둘 중 하나라도 채워지면 인정)
    power = spec.rated_power_kva or spec.rated_power_kw
    core: list[Any] = [
        spec.product_category,
        spec.rated_voltage_kv,
        spec.rated_current_a,
        power,
        spec.quantity,
    ]
    completeness = sum(1 for v in core if v is not None) / len(core)  # 0..1

    if category in ("IGBT", "SCR", "ABB장비"):
        return int(60 + 30 * completeness)
    if category == "수동소자":
        return int(50 + 20 * completeness)
    return int(40 * completeness)  # 혼합


class ClaudeAnalyzer:
    """M2 실가동 분석기. 외부 호출자가 try/except 없이 호출하므로 raise 금지."""

    def __init__(self, *, hwp_client: HwpAgentClient | None = None) -> None:
        self._hwp = hwp_client

    def analyze_notice(
        self,
        *,
        notice_no: str,
        title: str | None,
        raw: dict[str, Any] | None,
    ) -> AnalyzeResult:
        try:
            attachment_text: str | None = None
            if settings.llm_attachment_fetch and raw:
                attachment_text = fetch_first_attachment_text(raw, self._hwp)

            extraction = extract_specs_with_validation(
                bid_title=title or "",
                attachment_text=attachment_text,
                raw_json_summary=_summarize_raw_g2b(raw),
            )
            spec = extraction.spec

            category = map_elec_to_category(spec, title)
            fit_score = compute_fit_score(spec, category)

            analysis = {
                "source": "claude_schema_v1",
                "model": settings.anthropic_model,
                "elec_spec": spec.model_dump(exclude_none=True),
                "schema_valid": extraction.schema_valid,
                "schema_errors": extraction.schema_errors,
                "attachment_used": attachment_text is not None,
                "summary": (title or "")[:200],
            }
            return AnalyzeResult(category=category, fit_score=fit_score, analysis=analysis)
        except Exception as exc:
            log.exception("[claude_analyzer] failed for %s", notice_no)
            return AnalyzeResult(
                category="비관련",
                fit_score=0,
                analysis={"source": "claude", "error": str(exc)[:500]},
            )
