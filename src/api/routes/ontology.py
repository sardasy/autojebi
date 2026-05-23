"""Admin-protected SPARQL endpoint.

SELECT / ASK / CONSTRUCT / DESCRIBE 만 허용. UPDATE / INSERT / DELETE / LOAD / CLEAR / DROP / CREATE 차단.
입력 SPARQL 의 mutation 키워드 단순 정규식 차단 — 향후 SPARQL parser 기반 검증으로 강화 가능.
"""
from __future__ import annotations
import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import require_api_key
from src.ontology.fuseki_client import FusekiClient

router = APIRouter(prefix="/ontology", tags=["ontology"])
logger = logging.getLogger(__name__)

_fuseki: FusekiClient | None = None


def get_fuseki() -> FusekiClient:
    global _fuseki
    if _fuseki is None:
        _fuseki = FusekiClient()
    return _fuseki


class SparqlRequest(BaseModel):
    query: str
    format: str = "json"  # "json" → SELECT/ASK; "jsonld" → CONSTRUCT/DESCRIBE


_MUTATION_RE = re.compile(
    r"\b(INSERT|DELETE|DROP|CLEAR|LOAD|CREATE|COPY|MOVE|ADD)\b",
    re.IGNORECASE,
)


@router.post("/sparql", dependencies=[Depends(require_api_key)])
async def run_sparql(body: SparqlRequest):
    if _MUTATION_RE.search(body.query):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "mutations blocked — use ingest scripts (CLEAR/INSERT/DELETE 등은 차단)",
        )
    fuseki = get_fuseki()
    try:
        if body.format == "jsonld":
            result = await asyncio.to_thread(fuseki.query_jsonld, body.query)
        else:
            result = await asyncio.to_thread(fuseki.query_json, body.query)
    except Exception:
        logger.exception("SPARQL 실행 실패")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "ontology backend error")
    return result
