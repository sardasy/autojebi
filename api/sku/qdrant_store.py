"""Qdrant 컬렉션 관리 및 SKU 벡터 검색.

abb-bid-pipeline의 app/sku/qdrant_store.py에서 이식. settings.qdrant_collection_name
사용 (abb 원본은 하드코딩). 동기 클라이언트 그대로 (qdrant-client는 sync API 제공).
"""

from __future__ import annotations

import logging
import uuid

from qdrant_client import QdrantClient

from api.config import settings
from api.sku.schemas import AbbSku, SkuMatch

log = logging.getLogger(__name__)


def _sku_to_text(sku: AbbSku) -> str:
    """SKU를 임베딩 대상 텍스트로 직렬화."""
    parts: list[str] = [sku.name, sku.category, sku.description]
    if sku.voltage_kv is not None:
        parts.append(f"{sku.voltage_kv}kV")
    if sku.power_kva is not None:
        parts.append(f"{sku.power_kva}kVA")
    if sku.power_kw is not None:
        parts.append(f"{sku.power_kw}kW")
    if sku.current_a is not None:
        parts.append(f"{sku.current_a}A")
    if sku.phases is not None:
        parts.append("1phase" if sku.phases == 1 else "3phase")
    if sku.cooling_type:
        parts.append(sku.cooling_type)
    if sku.installation_type:
        parts.append(sku.installation_type)
    parts.extend(sku.tags)
    return " ".join(p for p in parts if p)


def _stable_id(sku_id: str) -> str:
    """sku_id → 재현 가능한 UUID 문자열 (재인덱싱 시 동일 포인트 덮어쓰기)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, sku_id))


class QdrantStore:
    """ABB SKU 컬렉션 CRUD + 검색 래퍼 (sync)."""

    def __init__(self, url: str | None = None, collection: str | None = None) -> None:
        self._url = url or settings.qdrant_url
        self._collection = collection or settings.qdrant_collection_name
        kwargs = {"url": self._url}
        if settings.qdrant_api_key:
            kwargs["api_key"] = settings.qdrant_api_key
        self._client = QdrantClient(**kwargs)

    @property
    def collection(self) -> str:
        return self._collection

    def ingest(self, skus: list[AbbSku]) -> int:
        if not skus:
            return 0
        documents = [_sku_to_text(sku) for sku in skus]
        ids = [_stable_id(sku.sku_id) for sku in skus]
        metadata = [sku.model_dump() for sku in skus]

        self._client.add(
            collection_name=self._collection,
            documents=documents,
            ids=ids,
            metadata=metadata,
        )
        log.info("[Qdrant] %d SKU 인덱싱 완료 → 컬렉션: %s", len(skus), self._collection)
        return len(skus)

    def search(self, query: str, limit: int = 5) -> list[SkuMatch]:
        results = self._client.query(
            collection_name=self._collection,
            query_text=query,
            limit=limit,
        )
        matches: list[SkuMatch] = []
        for r in results:
            try:
                sku = AbbSku.model_validate(r.metadata)
                matches.append(SkuMatch(sku=sku, score=round(float(r.score), 4)))
            except Exception as exc:  # noqa: BLE001
                log.warning("[Qdrant] 페이로드 역직렬화 실패: %s", exc)
        return matches

    def collection_exists(self) -> bool:
        try:
            return self._client.collection_exists(self._collection)
        except Exception as exc:  # noqa: BLE001
            log.warning("[Qdrant] collection_exists 실패: %s", exc)
            return False

    def count(self) -> int:
        if not self.collection_exists():
            return 0
        info = self._client.get_collection(self._collection)
        return info.points_count or 0
