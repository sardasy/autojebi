"""Fuseki SPARQL client.

읽기: GET /catalog/sparql (SELECT/CONSTRUCT/DESCRIBE/ASK)
쓰기: POST /catalog/update (SPARQL UPDATE, admin 인증 필요)
그래프 업로드: POST /catalog/data?graph=<uri> (Turtle body, admin 인증)

이 모듈은 BLOCKING `requests` 사용 — FastAPI 경로에서는 `asyncio.to_thread`
또는 (작은 카탈로그면) 동기 호출도 허용. ingest 스크립트는 동기 OK.
"""
from __future__ import annotations
import logging
from urllib.parse import urljoin
import requests
from rdflib import Graph
from SPARQLWrapper import SPARQLWrapper, JSON, JSONLD, POST, GET

from src.config import settings

logger = logging.getLogger(__name__)


class FusekiClient:
    """Minimal Fuseki client for SELECT / DESCRIBE / Turtle upload / SPARQL UPDATE."""

    def __init__(self, base_url: str | None = None, admin_password: str | None = None):
        self.base_url = (base_url or settings.fuseki_url).rstrip("/")
        # Jena Fuseki 의 Authoization 헤더는 admin 작업 (UPDATE / data upload) 에 필요.
        self._admin_auth = ("admin", admin_password or settings.fuseki_admin_password)

    # ------------------------------------------------------------------ read
    def query_json(self, sparql: str) -> dict:
        """SPARQL SELECT/ASK → standard SPARQL JSON results."""
        endpoint = f"{self.base_url}/sparql"
        w = SPARQLWrapper(endpoint)
        w.setReturnFormat(JSON)
        w.setMethod(GET)
        w.setQuery(sparql)
        return w.queryAndConvert()

    def query_jsonld(self, sparql: str) -> list:
        """SPARQL CONSTRUCT/DESCRIBE → JSON-LD (list of {@id, ...} 노드)."""
        import json as _json
        endpoint = f"{self.base_url}/sparql"
        w = SPARQLWrapper(endpoint)
        w.setReturnFormat(JSONLD)
        w.setMethod(GET)
        w.setQuery(sparql)
        result = w.queryAndConvert()
        # SPARQLWrapper 는 ConjunctiveGraph 를 반환 — JSON-LD 문자열로 직렬화 후 파싱.
        if hasattr(result, "serialize"):
            text = result.serialize(format="json-ld")
            if isinstance(text, bytes):
                text = text.decode("utf-8")
            return _json.loads(text)
        return result

    def ask(self, sparql: str) -> bool:
        out = self.query_json(sparql)
        return bool(out.get("boolean"))

    # ----------------------------------------------------------------- write
    def upload_turtle(self, turtle: str, named_graph: str | None = None) -> None:
        """POST Turtle body to Graph Store Protocol endpoint."""
        endpoint = f"{self.base_url}/data"
        params = {"graph": named_graph} if named_graph else {"default": ""}
        r = requests.post(
            endpoint,
            data=turtle.encode("utf-8"),
            headers={"Content-Type": "text/turtle; charset=utf-8"},
            params=params,
            auth=self._admin_auth,
            timeout=60,
        )
        if not r.ok:
            raise RuntimeError(f"Fuseki upload failed: {r.status_code} {r.text[:300]}")
        logger.info("Fuseki upload OK (graph=%s, %d bytes)", named_graph or "default", len(turtle))

    def upload_graph(self, graph: Graph, named_graph: str | None = None) -> None:
        self.upload_turtle(graph.serialize(format="turtle"), named_graph)

    def update(self, sparql_update: str) -> None:
        endpoint = f"{self.base_url}/update"
        r = requests.post(
            endpoint,
            data={"update": sparql_update},
            auth=self._admin_auth,
            timeout=60,
        )
        if not r.ok:
            raise RuntimeError(f"Fuseki update failed: {r.status_code} {r.text[:300]}")

    def clear_graph(self, named_graph: str) -> None:
        self.update(f"CLEAR GRAPH <{named_graph}>")

    # ----------------------------------------------------------------- meta
    def ping(self) -> bool:
        try:
            r = requests.get(urljoin(self.base_url.rsplit("/", 1)[0] + "/", "$/ping"), timeout=5)
            return r.ok
        except requests.RequestException:
            return False
