"""M14 — `python -m api.ontology` CLI 진입점.

사용:
    python -m api.ontology seed             # 멱등 upsert
    python -m api.ontology seed --dry-run   # 변경 없이 SeedReport만 출력
"""

from __future__ import annotations

import argparse
import json
import sys

from api.db import get_engine
from api.ontology.seed import seed_ontology


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="api.ontology")
    sub = parser.add_subparsers(dest="cmd", required=True)

    seed_p = sub.add_parser("seed", help="초기 통제어휘 멱등 upsert")
    seed_p.add_argument(
        "--dry-run",
        action="store_true",
        help="DB 변경 없이 SeedReport(insertable counts)만 출력",
    )

    args = parser.parse_args(argv)

    if args.cmd == "seed":
        engine = get_engine()
        report = seed_ontology(engine, dry_run=args.dry_run)
        # 한국어 안전 출력 (stdout 인코딩 강제)
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — stdout 인코딩 재설정은 best-effort
            pass
        print(json.dumps(dict(report), ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
