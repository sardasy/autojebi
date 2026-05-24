"""Read-only Catalog 조회 API. Fuseki 백엔드.

GET /api/v1/products            — brand/category/cert 필터, 페이지네이션
GET /api/v1/products/{sku_slug} — DESCRIBE JSON-LD
GET /api/v1/match-preview       — Phase 3 stub
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any
from fastapi import APIRouter, HTTPException, Query, status

from src.config import settings
from src.ontology import PREFIXES, NS_SKU
from src.ontology.fuseki_client import FusekiClient

router = APIRouter(tags=["products"])
logger = logging.getLogger(__name__)

_fuseki: FusekiClient | None = None


def get_fuseki() -> FusekiClient:
    global _fuseki
    if _fuseki is None:
        _fuseki = FusekiClient()
    return _fuseki


def _build_filter_query(
    brand: str | None, category: str | None, cert: str | None,
    limit: int, offset: int,
) -> str:
    """동적 필터 SPARQL — brand/category/cert 슬러그 전달."""
    where = ["?sku a cat:SKU ."]
    if brand:
        where.append(f"?sku cat:hasBrand exBrand:{brand} .")
    if category:
        where.append(f"?sku cat:belongsToCategory exCat:{category} .")
    if cert:
        # cert 슬러그로 부분 매칭
        where.append(
            f'?sku cat:hasCertification ?c . '
            f'?c cat:certifiedBy ?issuer . '
            f'FILTER(CONTAINS(LCASE(STR(?issuer)), "{cert.lower()}"))'
        )
    where.append("OPTIONAL { ?sku cat:hasBrand ?b }")
    where.append("OPTIONAL { ?sku cat:belongsToCategory ?cat0 }")
    where.append("OPTIONAL { ?sku cat:modelNumber ?model }")

    return PREFIXES + f"""
    SELECT ?sku ?b ?cat0 ?model
    FROM <{settings.fuseki_named_graph}>
    WHERE {{
        {' '.join(where)}
    }}
    ORDER BY ?sku
    LIMIT {limit} OFFSET {offset}
    """


def _flatten_bindings(sparql_json: dict) -> list[dict[str, Any]]:
    out = []
    for row in sparql_json.get("results", {}).get("bindings", []):
        out.append({k: v["value"] for k, v in row.items()})
    return out


@router.get("/products")
async def list_products(
    brand: str | None = Query(default=None, description="브랜드 슬러그 (e.g., 'abb')"),
    category: str | None = Query(default=None, description="카테고리 슬러그 (e.g., 'igbt-module')"),
    cert: str | None = Query(default=None, description="인증 발급기관 부분 매칭 (e.g., 'kepic')"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    fuseki = get_fuseki()
    q = _build_filter_query(brand, category, cert, limit, offset)
    try:
        result = await asyncio.to_thread(fuseki.query_json, q)
    except Exception:
        logger.exception("Fuseki query 실패")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "ontology backend unavailable")
    return {"limit": limit, "offset": offset, "items": _flatten_bindings(result)}


@router.get("/products/{sku_slug}")
async def get_product(sku_slug: str):
    sku_iri = f"<{NS_SKU}{sku_slug}>"
    q = PREFIXES + f"DESCRIBE {sku_iri} FROM <{settings.fuseki_named_graph}>"
    fuseki = get_fuseki()
    try:
        jsonld = await asyncio.to_thread(fuseki.query_jsonld, q)
    except Exception:
        logger.exception("Fuseki DESCRIBE 실패")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "ontology backend unavailable")
    if not jsonld:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SKU not found")
    return jsonld


@router.get("/match-preview")
async def match_preview(bid_id: str | None = None):
    """Phase 3 미구현 stub. 호출 시 200 + 명시적 안내."""
    return {
        "status": "not_implemented",
        "phase": 3,
        "message": "Bid↔SKU 매칭은 Phase 3 에서 구현됩니다.",
        "bid_id": bid_id,
    }
