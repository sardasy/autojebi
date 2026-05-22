import json
import logging
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from src.config import settings
from src.llm.prompts.summarize import SUMMARIZE_SYSTEM, SUMMARIZE_USER
from src.llm.structured_output import BidSummaryOutput

logger = logging.getLogger(__name__)

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

        try:
            if route["provider"] == "openai" and self._openai:
                return await self._openai_call(route["model"], SUMMARIZE_SYSTEM, prompt, route["max_tokens"])
            elif self._anthropic:
                return await self._anthropic_call(route["model"], SUMMARIZE_SYSTEM, prompt, route["max_tokens"])
        except Exception as e:
            logger.error(f"LLM 요약 실패: {e}")
        return None

    async def _openai_call(self, model: str, system: str, prompt: str, max_tokens: int) -> BidSummaryOutput | None:
        resp = await self._openai.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        return BidSummaryOutput.model_validate(json.loads(raw))

    async def _anthropic_call(self, model: str, system: str, prompt: str, max_tokens: int) -> BidSummaryOutput | None:
        resp = await self._anthropic.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return BidSummaryOutput.model_validate(json.loads(raw[start:end]))
