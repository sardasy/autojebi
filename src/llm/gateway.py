import json
import logging
from typing import TypeVar, Type
from pydantic import BaseModel
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from src.config import settings
from src.llm.prompts.summarize import SUMMARIZE_SYSTEM, SUMMARIZE_USER
from src.llm.prompts.product_spec import PRODUCT_SPEC_SYSTEM, PRODUCT_SPEC_USER
from src.llm.structured_output import BidSummaryOutput, ProductSpecOutput

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# 작업 유형별 LLM 라우팅 — 요약은 저비용 GPT, 분석/생성은 고품질 Claude
ROUTING = {
    "summarize": {"provider": "openai", "model": "gpt-4o-mini", "max_tokens": 1000},
    "analyze": {"provider": "anthropic", "model": "claude-sonnet-4-6", "max_tokens": 4000},
    "generate": {"provider": "anthropic", "model": "claude-sonnet-4-6", "max_tokens": 8000},
}


class LLMGateway:
    def __init__(self):
        self._anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def summarize_bid(self, bid_content: str) -> BidSummaryOutput | None:
        route = ROUTING["summarize"]
        prompt = SUMMARIZE_USER.format(bid_content=bid_content[:3000])

        # Primary (라우팅 지정 provider) → 실패 시 보조 provider 폴백.
        primary_provider = route["provider"]
        order = [primary_provider, "anthropic" if primary_provider == "openai" else "openai"]

        for provider in order:
            try:
                if provider == "openai" and self._openai:
                    return await self._openai_call(route["model"], SUMMARIZE_SYSTEM, prompt, route["max_tokens"])
                if provider == "anthropic" and self._anthropic:
                    # Anthropic fallback 용 모델: analyze 라우트와 동일 (Claude sonnet)
                    model = ROUTING["analyze"]["model"]
                    return await self._anthropic_call(model, SUMMARIZE_SYSTEM, prompt, route["max_tokens"])
            except Exception:
                logger.exception("LLM 요약 실패 (provider=%s) — 다음 provider 시도", provider)

        logger.warning("LLM 요약: 사용 가능한 provider 없음 또는 모두 실패")
        return None

    async def extract_product_spec(self, datasheet_text: str) -> ProductSpecOutput | None:
        """공급사 데이터시트 → ProductSpecOutput.

        분석 routing (Claude 우선, OpenAI 폴백) — 데이터시트는 표/단위 변환이 잦아
        고품질 모델이 안전. JSON-only 강제는 OpenAI 폴백 시 적용.
        """
        route = ROUTING["analyze"]
        prompt = PRODUCT_SPEC_USER.format(datasheet_text=datasheet_text[:8000])

        primary_provider = route["provider"]
        order = [primary_provider, "openai" if primary_provider == "anthropic" else "anthropic"]

        for provider in order:
            try:
                if provider == "anthropic" and self._anthropic:
                    return await self._anthropic_tool_call(
                        model=route["model"],
                        system=PRODUCT_SPEC_SYSTEM,
                        prompt=prompt,
                        max_tokens=route["max_tokens"],
                        schema_cls=ProductSpecOutput,
                        tool_name="emit_product_spec",
                    )
                if provider == "openai" and self._openai:
                    return await self._openai_json_call(
                        model=ROUTING["summarize"]["model"],
                        system=PRODUCT_SPEC_SYSTEM,
                        prompt=prompt,
                        max_tokens=route["max_tokens"],
                        schema_cls=ProductSpecOutput,
                    )
            except Exception:
                logger.exception("ProductSpec 추출 실패 (provider=%s) — 다음 provider 시도", provider)

        logger.warning("ProductSpec 추출: 사용 가능한 provider 없음 또는 모두 실패")
        return None

    # -------------------------------------------------- low-level dispatchers
    async def _openai_call(self, model: str, system: str, prompt: str, max_tokens: int) -> BidSummaryOutput | None:
        return await self._openai_json_call(model, system, prompt, max_tokens, BidSummaryOutput)

    async def _openai_json_call(
        self, model: str, system: str, prompt: str, max_tokens: int, schema_cls: Type[T]
    ) -> T | None:
        resp = await self._openai.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        return schema_cls.model_validate(json.loads(raw))

    async def _anthropic_call(self, model: str, system: str, prompt: str, max_tokens: int) -> BidSummaryOutput | None:
        return await self._anthropic_tool_call(
            model, system, prompt, max_tokens, BidSummaryOutput, "emit_bid_summary"
        )

    async def _anthropic_tool_call(
        self, model: str, system: str, prompt: str, max_tokens: int,
        schema_cls: Type[T], tool_name: str,
    ) -> T | None:
        tool = {
            "name": tool_name,
            "description": f"Emit a {schema_cls.__name__} in the required schema.",
            "input_schema": schema_cls.model_json_schema(),
        }
        resp = await self._anthropic.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                return schema_cls.model_validate(block.input)
        logger.warning("Anthropic 응답에 tool_use(%s) 블록 없음", tool_name)
        return None
