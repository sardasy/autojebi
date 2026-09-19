"""Create the missing default HWP template files (bid_form, proposal) through the Worker.

`data/` is gitignored, so a fresh machine has the template rows and mappings in the DB but no
files. This writes a field-only skeleton per registered template: exactly the active mapped
fields, nothing else, so `템플릿 필드 검사` and `HWP 생성` can run end to end.

The Worker can only author fields, not static text, so the result has no labels or official
form wording. It is a pipeline/validation skeleton, not a submission-ready form: open it in
Hancom Office and add the labels around the fields (or replace it with the official form carrying
the same field names) before real use.

Uses only the authenticated Worker endpoint (/document/create-template); no direct COM.
Never overwrites an existing template file.

    python -m tools.prepare_default_hwp_templates            # all registered defaults
    python -m tools.prepare_default_hwp_templates bid_form   # one key
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

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
        return {"template_key": key, "template_path": str(destination), "status": "exists_kept"}
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
    with destination.open("xb") as stream:  # never overwrite
        stream.write(content)
    return {"template_key": key, "template_path": str(destination), "sha256": checksum,
            "fields": layout.fields(), "status": "created_skeleton", "labels": "none_add_in_hancom"}


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(".env", override=False)
    for key in sys.argv[1:] or DEFAULT_KEYS:
        print(json.dumps(prepare(key), ensure_ascii=False))


if __name__ == "__main__":
    main()
