"""Anthropic Messages API 호출 (v2 작업대 전용).

요청 dict는 그대로 캐시 키(`llm_usage.reuse_result`)가 되므로 자격증명·클라이언트 옵션을
여기에 섞지 않는다. 자동 fallback/재시도 없음 (max_retries=0) — AGENTS.md §1 모델 선택 정책.
"""

from __future__ import annotations

from typing import Any

import anthropic

from api.config import settings


def generate(request: dict) -> Any:
    """tool_choice로 강제한 도구의 입력(JSON)을 반환. 도구 블록이 없으면 None."""
    tool_name = request["tool_choice"]["name"]
    payload = {k: v for k, v in request.items() if k != "provider"}
    with anthropic.Anthropic(
        api_key=settings.anthropic_api_key, max_retries=0, timeout=90
    ) as client:
        message = client.messages.create(**payload)
    return next(
        (b.input for b in message.content if b.type == "tool_use" and b.name == tool_name),
        None,
    )
