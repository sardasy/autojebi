"""공고 텍스트 → 전기 사양 추출 (Claude tool-use).

abb-bid-pipeline의 app/llm/extractor.py에서 이식. 주요 변경:
  - `pdf_bytes` 인자 제거 → 호출자가 첨부 텍스트(HWP/PDF/기타)를 직접 넘김.
    PDF 파일이 손에 있는 경우 `extract_pdf_text(bytes) -> str` 헬퍼는 그대로 노출.
  - 모델 이름은 `settings.anthropic_model` / `settings.anthropic_max_tokens` 동적.
  - `cache_control: ephemeral` 시스템 프롬프트 캐싱 유지.
  - tool_use 누락 시 빈 ElecSpec 반환 (예외 안 던짐).
"""

from __future__ import annotations

import io
import logging
from typing import Any

import anthropic
import pdfplumber

from api.config import settings
from api.llm.prompts import SYSTEM_PROMPT, build_user_message
from api.llm.schemas import ElecSpec

log = logging.getLogger(__name__)


_TOOL_DEF: dict[str, Any] = {
    "name": "extract_electrical_specs",
    "description": "Extract electrical specification details from the Korean procurement bid document.",
    "input_schema": ElecSpec.model_json_schema(),
}


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """pdfplumber로 PDF 바이트 → 텍스트."""
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text()
            if txt:
                text_parts.append(txt)
    return "\n".join(text_parts)


def extract_specs(
    bid_title: str,
    attachment_text: str | None = None,
    raw_json_summary: str | None = None,
) -> ElecSpec:
    """Claude API를 통해 전기 사양을 추출.

    Args:
        bid_title: 입찰공고 제목
        attachment_text: 첨부(HWP/PDF) 본문 텍스트. 호출자가 추출 책임.
        raw_json_summary: G2B API raw JSON 주요 필드 요약 문자열.

    Returns:
        ElecSpec — 관련 없는 공고면 모든 필드 None.
    """
    user_msg = build_user_message(bid_title, attachment_text, raw_json_summary)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    with client.messages.stream(
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[_TOOL_DEF],
        tool_choice={"type": "tool", "name": "extract_electrical_specs"},
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        message = stream.get_final_message()

    for block in message.content:
        if block.type == "tool_use" and block.name == "extract_electrical_specs":
            spec = ElecSpec.model_validate(block.input)
            log.info(
                "[LLM] 사양 추출 — 제품: %s, 전압: %s kV, 용량: %s kVA",
                spec.product_category,
                spec.rated_voltage_kv,
                spec.rated_power_kva,
            )
            return spec

    log.warning("[LLM] tool_use 블록 없음 — 빈 ElecSpec 반환")
    return ElecSpec()
