"""ElecSpec → Qdrant 쿼리 → SKU 매칭.

abb-bid-pipeline의 app/sku/matcher.py에서 이식. import 경로만 조정.
"""

from __future__ import annotations

import json
import logging

from api.llm.schemas import ElecSpec
from api.sku.qdrant_store import QdrantStore
from api.sku.schemas import SkuMatch

log = logging.getLogger(__name__)


def spec_to_query(spec: ElecSpec) -> str:
    """ElecSpec을 Qdrant 검색 쿼리 문자열로 변환."""
    parts: list[str] = []
    if spec.product_category:
        parts.append(spec.product_category)
    if spec.phases:
        parts.append(f"{spec.phases}상")
    if spec.rated_voltage_kv is not None:
        parts.append(f"{spec.rated_voltage_kv}kV")
    if spec.rated_power_kva is not None:
        parts.append(f"{spec.rated_power_kva}kVA")
    if spec.rated_power_kw is not None:
        parts.append(f"{spec.rated_power_kw}kW")
    if spec.rated_current_a is not None:
        parts.append(f"{spec.rated_current_a}A")
    if spec.breaking_capacity_ka is not None:
        parts.append(f"차단용량 {spec.breaking_capacity_ka}kA")
    if spec.cooling_type:
        parts.append(spec.cooling_type)
    if spec.installation_type:
        parts.append(spec.installation_type)
    if spec.protection_class:
        parts.append(spec.protection_class)
    parts.extend(spec.standards)
    if spec.notes:
        parts.append(spec.notes)

    query = " ".join(parts)
    if not query.strip():
        query = "전기 기자재"
    return query


def match_skus(
    spec: ElecSpec,
    limit: int = 5,
    store: QdrantStore | None = None,
) -> tuple[str, list[SkuMatch]]:
    """ElecSpec → (query, matches).

    store가 None이면 QdrantStore() 자체 생성. 테스트는 store를 주입할 수 있다.
    """
    query = spec_to_query(spec)
    if store is None:
        store = QdrantStore()

    if not store.collection_exists():
        log.warning("[matcher] Qdrant 컬렉션 없음 — SKU 인덱싱 필요")
        return query, []

    matches = store.search(query, limit=limit)
    log.info("[matcher] 쿼리='%s' → %d 매칭", query, len(matches))
    return query, matches


def match_skus_from_json(
    specs_json: str,
    limit: int = 5,
    store: QdrantStore | None = None,
) -> tuple[str, list[SkuMatch]]:
    try:
        data = json.loads(specs_json)
        spec = ElecSpec.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        log.error("[matcher] specs_json 파싱 실패: %s", exc)
        spec = ElecSpec()
    return match_skus(spec, limit=limit, store=store)
