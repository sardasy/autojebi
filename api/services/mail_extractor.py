"""KJEBI 알림메일 paste → 공고 메타 추출 서비스 (M12).

`api/llm/extractor.py`의 ElecSpec 패턴을 재사용 — Claude tool-use로
`KjebiMailExtraction`을 채워 받고, 추출 confidence를 함께 반환한다.

호출 측(api/routers/notices.py의 /extract-from-mail)이 notice_no 유무로
upsert 여부를 결정한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import anthropic

from api.config import settings
from api.llm.mail_prompts import MAIL_SYSTEM_PROMPT, build_mail_user_message
from api.llm.mail_schemas import KjebiMailExtraction

log = logging.getLogger(__name__)


_TOOL_DEF: dict[str, Any] = {
    "name": "extract_notice_from_mail",
    "description": "Extract Korean public-procurement notice metadata from a KJEBI alert mail.",
    "input_schema": KjebiMailExtraction.model_json_schema(),
}


# Confidence = (채워진 필드 수 / 전체 필드 수). notice_no 없으면 0.0 강제.
_FIELDS = list(KjebiMailExtraction.model_fields.keys())


@dataclass(frozen=True)
class MailExtractionResult:
    extracted: KjebiMailExtraction
    confidence: float
    errors: list[str]


def _compute_confidence(spec: KjebiMailExtraction) -> float:
    data = spec.model_dump()
    if not data.get("notice_no"):
        return 0.0
    filled = sum(1 for k in _FIELDS if data.get(k) not in (None, "", []))
    return round(filled / len(_FIELDS), 3)


def extract_notice_from_mail(raw_text: str) -> MailExtractionResult:
    """Claude를 통해 KJEBI 메일에서 공고 메타를 추출.

    Anthropic 키가 비었거나 호출이 실패하면 빈 추출 + 에러 메시지 반환.
    호출자는 result.extracted.notice_no가 있을 때만 upsert.
    """
    if not raw_text.strip():
        return MailExtractionResult(KjebiMailExtraction(), 0.0, ["empty input"])

    if not settings.anthropic_api_key:
        return MailExtractionResult(
            KjebiMailExtraction(), 0.0, ["ANTHROPIC_API_KEY not set"]
        )

    user_msg = build_mail_user_message(raw_text)
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            system=[
                {
                    "type": "text",
                    "text": MAIL_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[_TOOL_DEF],
            tool_choice={"type": "tool", "name": "extract_notice_from_mail"},
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            message = stream.get_final_message()
    except Exception as exc:  # noqa: BLE001
        log.exception("[mail_extract] Claude call failed")
        return MailExtractionResult(
            KjebiMailExtraction(), 0.0, [f"claude error: {str(exc)[:200]}"]
        )

    for block in message.content:
        if block.type == "tool_use" and block.name == "extract_notice_from_mail":
            try:
                spec = KjebiMailExtraction.model_validate(block.input)
            except Exception as exc:  # noqa: BLE001
                log.warning("[mail_extract] tool_use input invalid: %s", exc)
                return MailExtractionResult(
                    KjebiMailExtraction(), 0.0, [f"schema error: {str(exc)[:200]}"]
                )
            confidence = _compute_confidence(spec)
            log.info(
                "[mail_extract] notice_no=%s title=%s confidence=%.2f",
                spec.notice_no,
                (spec.title or "")[:40],
                confidence,
            )
            return MailExtractionResult(spec, confidence, [])

    log.warning("[mail_extract] no tool_use block — returning empty extraction")
    return MailExtractionResult(KjebiMailExtraction(), 0.0, ["no tool_use block"])
