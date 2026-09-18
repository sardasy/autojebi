"""Explicit template preparation through the authenticated Worker, never direct COM."""
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from api.db import require_engine
from api.db.tables import document_field_mappings, hwp_templates
from api.hwp_worker.layout import Block, Layout, Run
from api.services.hwp_agent_client import HwpAgentClient
from api.workspace.hwp_layout import validate_created


def prepare_template() -> dict:
    engine = require_engine()
    key = "proposal_layout_v1"
    with engine.connect() as conn:
        existing = conn.execute(select(hwp_templates).where(hwp_templates.c.template_key == key)).mappings().first()
        if existing:
            raise ValueError("template_already_registered: inspect existing version instead of overwriting")
    root = Path(os.getenv("WORKSPACE_DATA_DIR", "data/workspace")).resolve()
    output_root = Path(os.getenv("HWP_OUTPUT_ROOT", str(root / "exports"))).resolve(strict=True)
    template_root = Path(os.getenv("HWP_TEMPLATE_ROOT", "data")).resolve(strict=True)
    operation = uuid4().hex
    output = output_root / f"template-{operation}.hwp"
    layout = Layout(blocks=[Block(kind="paragraph", runs=[Run(field="proposal_body")])])
    client = HwpAgentClient(timeout_s=120, retries=1)
    if not client.diagnostics()["available"]:
        raise ValueError("worker_not_ready")
    report = client.create_template(operation_id=operation, output_path=str(output), layout=layout.model_dump())
    checksum = validate_created(report, output, layout, None)
    folder = template_root / "templates"
    if folder.is_symlink():
        raise ValueError("linked_template_folder")
    folder.mkdir(exist_ok=True)
    destination = folder / f"proposal-layout-{operation}.hwp"
    content = output.read_bytes()
    if hashlib.sha256(content).hexdigest() != checksum:
        raise ValueError("template_changed_before_registration")
    with destination.open("xb") as stream:
        stream.write(content)
    with engine.begin() as conn:
        result = conn.execute(hwp_templates.insert().values(
            template_key=key, kind="proposal", name="제안서 · 실무 서식", render_mode=key,
            template_path=str(destination), template_version=operation, active=True))
        template_id = result.inserted_primary_key[0]
        conn.execute(document_field_mappings.insert().values(
            template_id=template_id, hwp_field_name="proposal_body", context_path="proposal.body",
            value_type="string", required=True, transform="none", sort_order=10, active=True))
    return {"template_key": key, "template_path": str(destination), "sha256": checksum,
            "layout_review": "pending", "operation_id": operation}
