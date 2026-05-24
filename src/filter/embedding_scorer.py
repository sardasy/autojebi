import logging
import numpy as np
from openai import AsyncOpenAI
from src.config import settings
from src.filter.energy_keywords import ALL_KEYWORDS

logger = logging.getLogger(__name__)


class EmbeddingScorer:
    def __init__(self):
        self._client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self._ref_embedding: list[float] | None = None
        self._ref_text = " ".join(ALL_KEYWORDS[: settings.embedding_reference_keyword_count])

    async def _get_ref_embedding(self) -> list[float]:
        if self._ref_embedding is None:
            resp = await self._client.embeddings.create(
                model="text-embedding-3-small",
                input=self._ref_text,
            )
            self._ref_embedding = resp.data[0].embedding
        return self._ref_embedding

    async def score(self, text: str) -> float:
        if not self._client:
            return 0.5  # OpenAI 키 없을 때 중립값 반환
        try:
            ref = await self._get_ref_embedding()
            resp = await self._client.embeddings.create(
                model="text-embedding-3-small",
                input=text[: settings.embedding_text_limit],
            )
            vec = resp.data[0].embedding
            similarity = float(np.dot(ref, vec) / (np.linalg.norm(ref) * np.linalg.norm(vec)))
            return max(0.0, similarity)
        except Exception:
            logger.exception("임베딩 스코어링 실패")
            return 0.0
