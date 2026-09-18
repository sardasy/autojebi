"""Read-only database fingerprints and file-reference coverage for restore rehearsals."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, Column, Integer, MetaData, Table, create_engine, inspect, select


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str, allow_nan=False).encode()


def fingerprint_database(engine: Any) -> dict:
    result = {}
    sequences = {}
    with engine.connect() as conn:
        inspector = inspect(conn)
        for name in sorted(inspector.get_table_names()):
            table = Table(name, MetaData(), autoload_with=conn)
            digests = []
            for row in conn.execute(select(table)).mappings():
                if len(digests) >= 1_000_000:
                    raise ValueError("database audit row limit exceeded")
                digests.append(hashlib.sha256(_canonical(dict(row))).digest())
            schema = {
                "columns": [
                    {key: str(col[key]) if key == "type" else col.get(key)
                     for key in ("name", "type", "nullable", "default")}
                    for col in inspector.get_columns(name)
                ],
                "primary_key": inspector.get_pk_constraint(name),
                "unique": inspector.get_unique_constraints(name),
                "foreign_keys": inspector.get_foreign_keys(name),
                "checks": inspector.get_check_constraints(name),
                "indexes": inspector.get_indexes(name),
            }
            result[name] = {
                "rows": len(digests),
                "data_sha256": hashlib.sha256(b"".join(sorted(digests))).hexdigest(),
                "schema_sha256": hashlib.sha256(_canonical(schema)).hexdigest(),
            }
        if conn.dialect.name == "postgresql":
            for name in sorted(inspector.get_sequence_names()):
                sequence = Table(name, MetaData(), Column("last_value", Integer), Column("is_called", Boolean))
                sequences[name] = dict(conn.execute(select(sequence)).mappings().one())
    return {"version": 1, "tables": result, "sequences": sequences}


def compare_databases(baseline: dict, restored: dict) -> dict:
    before, after = baseline["tables"], restored["tables"]
    common = before.keys() & after.keys()
    missing, extra = sorted(before.keys() - after.keys()), sorted(after.keys() - before.keys())
    data_differences = sorted(
        name for name in common
        if any(before[name][key] != after[name][key] for key in ("rows", "data_sha256"))
    )
    schema_differences = sorted(
        name for name in common if before[name]["schema_sha256"] != after[name]["schema_sha256"]
    )
    sequences_equal = baseline["sequences"] == restored["sequences"]
    return {
        "equal": baseline == restored,
        "data_equal": not (missing or extra or data_differences),
        "schema_equal": not (missing or extra or schema_differences),
        "sequences_equal": sequences_equal,
        "missing_tables": missing, "extra_tables": extra,
        "data_differences": data_differences, "schema_differences": schema_differences,
    }


def file_references(engine: Any, project_root: Path, template_root: Path) -> list[dict]:
    refs = []

    def add(kind: str, identifier: str, path: Any, checksum: Any, base: Path = project_root):
        if not isinstance(path, str) or not path.strip():
            return
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = base / candidate
        refs.append({"kind": kind, "id": str(identifier), "path": os.path.abspath(candidate), "sha256": checksum})

    def documents(kind: str, identifier: str, inputs: dict):
        for doc in inputs.get("documents") or []:
            add(kind, f"{identifier}/{doc.get('id', '')}", doc.get("storage_path"), doc.get("sha256"))

    with engine.connect() as conn:
        names = set(inspect(conn).get_table_names())

        def rows(name: str):
            if name not in names:
                return []
            return conn.execute(select(Table(name, MetaData(), autoload_with=conn))).mappings()

        for row in rows("notice_workspaces"):
            documents("workspace", row["notice_no"], row["inputs"])
        for row in rows("company_assets"):
            doc = row["file"]
            add("company_asset", row["id"], doc.get("storage_path"), doc.get("sha256"))
        for row in rows("workspace_jobs"):
            documents("job_snapshot", row["id"], row["snapshot"])
            result = row["result"] or {}
            add("job_artifact", row["id"], result.get("artifact"), result.get("sha256"))
        for row in rows("workspace_reviews"):
            documents("review_history", row["id"], (row["details"] or {}).get("previous_inputs") or {})
        for row in rows("bid_pipeline"):
            automation = (row["analysis"] or {}).get("document_automation") or {}
            for doc in automation.get("uploads") or []:
                add("legacy_upload", f"{row['notice_no']}/{doc.get('id', '')}", doc.get("storage_path"), doc.get("sha256"))
        for row in rows("notice_exports"):
            if not row["deleted_at"]:
                add("legacy_export", row["id"], row["output_path"], row["sha256"])
        for row in rows("hwp_templates"):
            add("template", row["template_key"], row["template_path"], None, template_root)
        for row in rows("proposal_documents"):
            add("proposal_evidence", row["id"], row["file_path"], row["checksum"])
    return refs


def audit_references(references: list[dict], manifest: dict) -> dict:
    """Use only a manifest returned by verify_backup; never open DB-provided paths."""
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    roots = {label: Path(root) for label, root in manifest["roots"].items()}
    issues, checked, path_only = [], 0, 0
    for ref in references:
        path = Path(ref["path"])
        matches = [
            f"files/{label}/{path.relative_to(root).as_posix()}"
            for label, root in roots.items() if path.is_relative_to(root)
        ]
        entry = entries.get(matches[0]) if len(matches) == 1 else None
        code = None
        if entry is None:
            code = "not_archived"
        elif ref.get("sha256"):
            expected = ref["sha256"]
            if not isinstance(expected, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
                code = "unsupported_checksum"
            elif expected.lower() != entry["sha256"].lower():
                code = "database_file_hash_mismatch"
            else:
                checked += 1
        else:
            path_only += 1
        if code:
            issues.append({"kind": ref["kind"], "id": ref["id"], "code": code})
    return {
        "reference_count": len(references), "unique_paths": len({r["path"] for r in references}),
        "database_hash_matches": checked, "path_only_matches": path_only,
        "issues": issues, "complete": not issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only backup database audit")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--project-root", type=Path, required=True)
    capture.add_argument("--template-root", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--baseline", type=Path, required=True)
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--archive-sha256", required=True)
    verify.add_argument("--restored-root", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not os.getenv("DATABASE_URL"):
        parser.error("DATABASE_URL must be explicitly set")
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        if args.command == "capture":
            result = {
                "fingerprint": fingerprint_database(engine),
                "references": file_references(engine, args.project_root.resolve(), args.template_root.resolve()),
                "project_root": str(args.project_root.resolve()),
                "template_root": str(args.template_root.resolve()),
            }
            summary = {"tables": len(result["fingerprint"]["tables"]), "references": len(result["references"])}
        else:
            from api.workspace.file_backup import verify_backup, verify_restored

            manifest = verify_backup(args.archive, args.archive_sha256)
            file_result = verify_restored(manifest, args.restored_root)
            relative = args.baseline.resolve().relative_to(args.restored_root.resolve()).as_posix()
            entry = next((e for e in manifest["entries"] if e["path"] == relative), None)
            if entry is None:
                raise ValueError("baseline must be included in the verified restore")
            baseline_bytes = args.baseline.read_bytes()
            if hashlib.sha256(baseline_bytes).hexdigest() != entry["sha256"]:
                raise ValueError("baseline changed after restore verification")
            baseline = json.loads(baseline_bytes)
            current = fingerprint_database(engine)
            comparison = compare_databases(baseline["fingerprint"], current)
            refs = file_references(engine, Path(baseline["project_root"]), Path(baseline["template_root"]))
            coverage = audit_references(refs, manifest)
            result = {
                "database_equal": comparison["equal"], "database_comparison": comparison,
                "references_equal": sorted(refs, key=lambda r: _canonical(r)) == sorted(baseline["references"], key=lambda r: _canonical(r)),
                "file_restore": file_result, "coverage": coverage,
                "archive_sha256": args.archive_sha256,
            }
            result["complete"] = result["database_equal"] and result["references_equal"] and coverage["complete"]
            summary = {key: result[key] for key in ("database_equal", "references_equal", "complete")}
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps(summary))
        if args.command == "verify" and not result["complete"]:
            raise SystemExit(2)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
