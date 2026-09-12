"""Explicit evaluation/release tools. No provider calls or automatic publication."""
import argparse
import json
from pathlib import Path

from api.specifications.evaluation import evaluate


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate_parser = sub.add_parser("evaluate")
    evaluate_parser.add_argument("--dataset", type=Path, required=True)
    evaluate_parser.add_argument("--results", type=Path, required=True)
    evaluate_parser.add_argument("--manifest-hash", required=True)
    evaluate_parser.add_argument("--output", type=Path, required=True)
    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("--notice", required=True)
    publish_parser.add_argument("--generation", required=True)
    publish_parser.add_argument("--report", type=Path, required=True)
    sub.add_parser("graph-schema", help="Explicitly provision fixed graph constraints")
    args = parser.parse_args()
    if args.command == "evaluate":
        report = evaluate(json.loads(args.dataset.read_text(encoding="utf-8")),
                          json.loads(args.results.read_text(encoding="utf-8")), args.manifest_hash)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print("Evaluation recorded. Publication requires a separate explicit command.")
    elif args.command == "graph-schema":
        from api.specifications.indexing import provision_graph_schema
        provision_graph_schema()
        print("Validation graph constraints provisioned. No corpus or business state changed.")
    else:
        from api.db import require_engine
        from api.specifications.indexing import publish
        with require_engine().begin() as conn:
            publish(conn, args.notice, args.generation, json.loads(args.report.read_text(encoding="utf-8")))
        print("Search generation published. Human business decisions unchanged.")


if __name__ == "__main__":
    main()
