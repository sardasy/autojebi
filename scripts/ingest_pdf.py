"""PDF datasheet → LLM extract → triples → SHACL → Fuseki.

Usage:
    python -m scripts.ingest_pdf data/catalog/datasheets/abb_xxx.pdf [--dry-run]
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm.gateway import LLMGateway  # noqa: E402
from src.ontology.triple_builder import build_sku_triples  # noqa: E402
from src.ontology.validator import validate  # noqa: E402
from src.ontology.fuseki_client import FusekiClient  # noqa: E402
from src.config import settings  # noqa: E402


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ingest_pdf")


def extract_text(pdf_path: Path, max_chars: int = 8000) -> str:
    chunks: list[str] = []
    total = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            chunks.append(t)
            total += len(t)
            if total >= max_chars:
                break
    return ("\n".join(chunks))[:max_chars]


async def run(pdf_path: Path, *, dry_run: bool = False) -> int:
    if sys.platform == "win32":
        # asyncpg / openai async — selector loop 호환
        pass

    text = extract_text(pdf_path)
    if not text.strip():
        logger.error("PDF 텍스트 추출 실패 (빈 결과): %s", pdf_path)
        return 2

    gw = LLMGateway()
    spec = await gw.extract_product_spec(text)
    if not spec:
        logger.error("LLM 추출 실패: %s", pdf_path)
        return 3

    logger.info("추출 SKU: %s / %s / %s", spec.brand, spec.category, spec.model_number)
    g = build_sku_triples(
        spec,
        provenance=f"{pdf_path.name}#llm",
        datasheet_url=None,
    )
    conforms, report = validate(g)
    if not conforms:
        logger.error("SHACL 검증 실패:\n%s", report[:1000])
        return 4

    logger.info("triple count: %d", len(g))

    if dry_run:
        logger.info("Dry-run — Fuseki 업로드 건너뜀")
        return 0

    cli = FusekiClient()
    if not cli.ping():
        logger.error("Fuseki 연결 실패 (%s)", cli.base_url)
        return 5
    cli.upload_graph(g, named_graph=settings.fuseki_named_graph)
    logger.info("Fuseki upload OK (graph=%s)", settings.fuseki_named_graph)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf_path", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(args.pdf_path, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
