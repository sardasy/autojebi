"""CSV → triples → SHACL → Fuseki ingest.

Usage:
    python -m scripts.ingest_csv data/catalog/skus_seed.csv [--dry-run]

CSV 컬럼 (모두 string, 빈 셀 허용):
    sku_id, brand, category, model_number,
    voltage_v, current_a, power_w, switching_freq_hz,
    certifications,  # 예: "KEPIC-EN:KEPIC; UL1741:UL"
    datasheet_url
"""
from __future__ import annotations
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from rdflib import Graph

# 스크립트 실행 시 src 경로 부트스트랩
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm.structured_output import ProductSpecOutput, CertificationSpec  # noqa: E402
from src.ontology.triple_builder import build_sku_triples, merge  # noqa: E402
from src.ontology.validator import validate  # noqa: E402
from src.ontology.fuseki_client import FusekiClient  # noqa: E402
from src.config import settings  # noqa: E402


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ingest_csv")


def _parse_certs(cell: str | float | None) -> list[CertificationSpec]:
    if cell is None or (isinstance(cell, float) and pd.isna(cell)) or not str(cell).strip():
        return []
    out: list[CertificationSpec] = []
    for tok in str(cell).split(";"):
        tok = tok.strip()
        if not tok:
            continue
        # 형식: "이름:발급기관" — 발급기관 없으면 이름으로 fallback
        if ":" in tok:
            name, issuer = tok.split(":", 1)
        else:
            name, issuer = tok, tok
        out.append(CertificationSpec(name=name.strip(), issuer=issuer.strip()))
    return out


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def row_to_spec(row: dict, row_idx: int) -> ProductSpecOutput:
    sku_id = str(row.get("sku_id") or "").strip()
    brand = str(row.get("brand") or "").strip()
    model_number = str(row.get("model_number") or "").strip()
    if not sku_id or not brand or not model_number:
        raise ValueError(f"missing required field (sku_id/brand/model_number)")
    return ProductSpecOutput(
        sku_id=sku_id,
        brand=brand,
        category=str(row.get("category") or "").strip(),
        model_number=model_number,
        voltage_v=_num(row.get("voltage_v")),
        current_a=_num(row.get("current_a")),
        power_w=_num(row.get("power_w")),
        switching_freq_hz=_num(row.get("switching_freq_hz")),
        certifications=_parse_certs(row.get("certifications")),
    )


def run(csv_path: Path, *, dry_run: bool = False, out_dir: Path | None = None) -> int:
    df = pd.read_csv(csv_path).fillna("")
    logger.info("CSV %s: %d rows", csv_path, len(df))

    valid_graphs: list[Graph] = []
    errors_log: list[str] = []

    for idx, row in df.iterrows():
        row_d = row.to_dict()
        try:
            spec = row_to_spec(row_d, idx)
        except Exception as e:
            errors_log.append(f"row {idx} ({row_d.get('sku_id','?')}): parse {e}")
            continue

        g = build_sku_triples(
            spec,
            provenance=f"{csv_path.name}#row{idx}",
            datasheet_url=row_d.get("datasheet_url") or None,
        )
        conforms, report = validate(g)
        if not conforms:
            errors_log.append(f"row {idx} ({spec.sku_id}): SHACL\n{report}")
            continue
        valid_graphs.append(g)

    merged = merge(valid_graphs)
    out_dir = out_dir or (csv_path.parent / "generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ttl_path = out_dir / f"skus_{ts}.ttl"
    ttl_path.write_text(merged.serialize(format="turtle"), encoding="utf-8")
    logger.info("Valid rows: %d / %d → %s", len(valid_graphs), len(df), ttl_path)

    if errors_log:
        err_path = out_dir / "errors.log"
        err_path.write_text("\n\n".join(errors_log), encoding="utf-8")
        logger.warning("Errors: %d → %s", len(errors_log), err_path)

    if dry_run:
        logger.info("Dry-run — Fuseki 업로드 건너뜀")
        return 0 if not errors_log else 1

    cli = FusekiClient()
    if not cli.ping():
        logger.error("Fuseki 연결 실패 (%s)", cli.base_url)
        return 2
    cli.upload_graph(merged, named_graph=settings.fuseki_named_graph)
    logger.info("Fuseki upload OK (graph=%s)", settings.fuseki_named_graph)
    return 0 if not errors_log else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="Fuseki 업로드 없이 .ttl 생성만")
    args = ap.parse_args()
    return run(args.csv_path, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
