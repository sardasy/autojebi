"""Create the missing default HWP template files (bid_form, proposal) through the Worker.

`data/` is gitignored, so a fresh machine has the template rows and mappings in the DB but no
files. This writes a field-only skeleton per registered template: exactly the active mapped
fields, nothing else, so `템플릿 필드 검사` and `HWP 생성` can run end to end.

The Worker can only author fields, not static text, so the result has no labels or official
form wording. It is a pipeline/validation skeleton, not a submission-ready form: open it in
Hancom Office and add the labels around the fields (or replace it with the official form carrying
the same field names), then explicitly register the reviewed source before real use.

Uses only the authenticated Worker endpoint (/document/create-template); no direct COM.
Never overwrites an existing template file.

    python -m tools.prepare_default_hwp_templates            # all registered defaults
    python -m tools.prepare_default_hwp_templates bid_form   # one key
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from api.parsing.hwp_validation import read_hwp_output, validate_hwp_content
from api.workspace.template_provenance import (
    inspect_provenance,
    register_source_form,
    write_skeleton_metadata,
)

DEFAULT_KEYS = ("bid_form", "proposal")
LONG_TRANSFORMS = {"truncate_1000", "none"}


def build_layout(fields: list[dict]):
    """Title as heading, short values in a two-column table, long text as paragraphs."""
    from api.hwp_worker.layout import Block, Layout, Run

    names = [f["hwp_field_name"] for f in fields]
    heading = [n for n in names if n == "title"]
    long_text = [f["hwp_field_name"] for f in fields
                 if f["hwp_field_name"] != "title" and f["transform"] in LONG_TRANSFORMS]
    short = [n for n in names if n not in heading and n not in long_text]
    if len(short) % 2:
        long_text.insert(0, short.pop())
    blocks = [Block(kind="heading", level=1, runs=[Run(field=n)]) for n in heading]
    if short:
        blocks.append(Block(kind="table", rows=[[[Run(field=a)], [Run(field=b)]]
                                                for a, b in zip(short[::2], short[1::2], strict=True)]))
    blocks += [Block(kind="paragraph", runs=[Run(field=n)]) for n in long_text]
    return Layout(blocks=blocks)


def prepare(key: str) -> dict:
    from api.db import require_engine
    from api.db.tables import document_field_mappings, hwp_templates
    from api.services.hwp_agent_client import HwpAgentClient
    from api.workspace.hwp_layout import validate_created

    with require_engine().connect() as conn:
        template = conn.execute(select(hwp_templates).where(hwp_templates.c.template_key == key)).mappings().first()
        if not template:
            raise ValueError(f"template_not_registered: {key} (run `python -m api.hwp_fields seed` first)")
        fields = [dict(r) for r in conn.execute(
            select(document_field_mappings).where(
                document_field_mappings.c.template_id == template["id"],
                document_field_mappings.c.active.is_(True),
            ).order_by(document_field_mappings.c.sort_order)).mappings()]
    if not fields:
        raise ValueError(f"no_active_mappings: {key}")
    template_root = Path(os.getenv("HWP_TEMPLATE_ROOT", "data")).resolve(strict=True)
    destination = Path(template["template_path"])
    destination = (destination if destination.is_absolute() else template_root / destination).resolve()
    if not destination.is_relative_to(template_root) or destination.suffix.lower() != ".hwp":
        raise ValueError(f"template_path_not_allowed: {destination}")
    if destination.exists():
        return {"template_key": key, "template_path": str(destination), "status": "exists_kept",
                "provenance": inspect_provenance(dict(template))}
    if destination.parent.is_symlink():
        raise ValueError("linked_template_folder")

    data_root = Path(os.getenv("WORKSPACE_DATA_DIR", "data/workspace")).resolve()
    output_root = Path(os.getenv("HWP_OUTPUT_ROOT", str(data_root / "exports"))).resolve(strict=True)
    operation = uuid4().hex
    output = output_root / f"template-{operation}.hwp"
    layout = build_layout(fields)
    client = HwpAgentClient(timeout_s=120, retries=1)
    if not client.diagnostics()["available"]:
        raise ValueError("worker_not_ready")
    report = client.create_template(operation_id=operation, output_path=str(output), layout=layout.model_dump())
    checksum = validate_created(report, output, layout, None)
    content = output.read_bytes()
    if hashlib.sha256(content).hexdigest() != checksum:
        raise ValueError("template_changed_before_registration")
    destination.parent.mkdir(exist_ok=True)
    write_skeleton_metadata(destination, key, checksum, operation)
    with destination.open("xb") as stream:  # never overwrite
        stream.write(content)
    return {"template_key": key, "template_path": str(destination), "sha256": checksum,
            "fields": layout.fields(), "status": "created_skeleton", "labels": "validation_only",
            "provenance": inspect_provenance(dict(template))}


def register_existing(args: argparse.Namespace) -> dict:
    """Explicit local administrator operation; never infer a file's origin from its name/size."""
    from api.db import require_engine
    from api.db.tables import hwp_templates

    key = args.register_source_form or args.mark_existing_skeleton
    with require_engine().connect() as conn:
        row = conn.execute(select(hwp_templates).where(hwp_templates.c.template_key == key)).mappings().first()
    if row is None:
        raise ValueError("template_not_registered")
    template = dict(row)
    if args.register_source_form:
        return register_source_form(template, args.expected_sha256,
            source_reference=args.source_reference, reviewer_id=args.reviewer_id,
            review_note=args.review_note, human_reviewed=args.labels_and_official_wording_checked,
            expected_metadata_sha256=args.expected_metadata_sha256)
    if not args.confirm_validation_only:
        raise ValueError("explicit_validation_only_confirmation_required")
    proof = inspect_provenance(template)
    if proof["template_sha256"] != args.expected_sha256 or not proof["generation_allowed"]:
        raise ValueError("template_hash_confirmation_required")
    path = Path(proof["template_path"])
    validate_hwp_content(read_hwp_output(path), path.suffix.lower())
    write_skeleton_metadata(path, key, args.expected_sha256, uuid4().hex)
    return inspect_provenance(template)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keys", nargs="*")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--register-source-form", metavar="KEY")
    actions.add_argument("--mark-existing-skeleton", metavar="KEY")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--expected-metadata-sha256")
    parser.add_argument("--source-reference")
    parser.add_argument("--reviewer-id")
    parser.add_argument("--review-note")
    parser.add_argument("--labels-and-official-wording-checked", action="store_true")
    parser.add_argument("--confirm-validation-only", action="store_true")
    args = parser.parse_args()
    if args.register_source_form or args.mark_existing_skeleton:
        if args.keys or not args.expected_sha256:
            parser.error("registration requires --expected-sha256 and no positional keys")
        print(json.dumps(register_existing(args), ensure_ascii=False))
        return
    for key in args.keys or DEFAULT_KEYS:
        print(json.dumps(prepare(key), ensure_ascii=False))


if __name__ == "__main__":
    main()
