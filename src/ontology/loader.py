"""T-Box + shapes 를 Fuseki 의 named graph 로 부트스트랩 업로드.

별도 graph 로 분리:
- <https://autojebi.local/graphs/tbox>    : 온톨로지 클래스/속성
- <https://autojebi.local/graphs/shapes>  : SHACL shapes
- (데이터는 settings.fuseki_named_graph 사용)
"""
from __future__ import annotations
import logging
from src.ontology import CATALOG_TTL, SHAPES_TTL
from src.ontology.fuseki_client import FusekiClient

logger = logging.getLogger(__name__)

TBOX_GRAPH = "https://autojebi.local/graphs/tbox"
SHAPES_GRAPH = "https://autojebi.local/graphs/shapes"


def bootstrap(client: FusekiClient | None = None) -> None:
    cli = client or FusekiClient()
    # idempotent: 매번 clear → upload.
    for ttl_path, graph_uri in ((CATALOG_TTL, TBOX_GRAPH), (SHAPES_TTL, SHAPES_GRAPH)):
        ttl = ttl_path.read_text(encoding="utf-8")
        try:
            cli.clear_graph(graph_uri)
        except RuntimeError:
            # 첫 부트스트랩일 때는 graph 가 없을 수도 있음 — 무시
            pass
        cli.upload_turtle(ttl, named_graph=graph_uri)
    logger.info("Bootstrap complete: T-Box + shapes uploaded to Fuseki")
