"""One-shot Fuseki 부트스트랩: T-Box + shapes 업로드 후 헬스체크.

Usage:
    python -m scripts.bootstrap_fuseki
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    from src.ontology.fuseki_client import FusekiClient
    from src.ontology.loader import bootstrap

    cli = FusekiClient()
    if not cli.ping():
        logger.error("Fuseki 연결 실패 (%s) — `docker compose up -d fuseki` 후 재시도", cli.base_url)
        return 2

    bootstrap(cli)

    # 검증: T-Box 가 적재됐는지 ASK (named graph 명시)
    sparql = """
    PREFIX cat: <https://autojebi.local/ontology/catalog#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    ASK {
      GRAPH <https://autojebi.local/graphs/tbox> { cat:SKU a owl:Class }
    }
    """
    if cli.ask(sparql):
        logger.info("Bootstrap 검증 OK — cat:SKU 클래스 인식됨")
        return 0
    logger.error("Bootstrap 검증 실패 — T-Box 가 적재되지 않음")
    return 1


if __name__ == "__main__":
    sys.exit(main())
