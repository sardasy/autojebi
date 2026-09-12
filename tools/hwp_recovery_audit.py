"""Read-only source audit; writes a new audit directory without acknowledging recovery."""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, select

from api.routers.notices import document_field_mappings, hwp_templates
from api.services.hwp_agent_client import HwpAgentClient
from api.workspace.tables import jobs


def main() -> None:
    load_dotenv(override=False)
    root = Path(os.environ["WORKSPACE_DATA_DIR"]).resolve(strict=True)
    output = Path(os.environ["HWP_OUTPUT_ROOT"]).resolve(strict=True)
    target = root / "recovery-audit" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target.mkdir(parents=True, exist_ok=False)
    marker = output / ".hwp-active.json"
    if marker.is_file():
        if marker.is_symlink() or marker.stat().st_size > 16384:
            raise ValueError("Unsafe marker")
        original = marker.read_bytes()
        (target / "marker.json").write_bytes(original)
    inventory = []
    for path in output.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            inventory.append(
                {
                    "path": str(path.relative_to(output)),
                    "size": path.stat().st_size,
                    "sha256": checksum,
                }
            )
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        configuration = {
            table.name: [dict(row) for row in conn.execute(select(table)).mappings()]
            for table in (hwp_templates, document_field_mappings)
        }
        rows = (
            conn.execute(
                select(
                    jobs.c.id,
                    jobs.c.kind,
                    jobs.c.status,
                    jobs.c.input_version,
                    jobs.c.notice_no,
                    jobs.c.created_at,
                    jobs.c.finished_at,
                ).where(jobs.c.kind.in_(["hwp", "hwp_inspect", "extract"]))
            )
            .mappings()
            .all()
        )
    (target / "template-config.json").write_text(
        json.dumps(configuration, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "operator_confirmation": "pending",
        "worker": HwpAgentClient(timeout_s=3, retries=1).diagnostics(),
        "files": inventory,
        "jobs": [dict(row) for row in rows],
    }
    (target / "inventory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"audit_directory": str(target), "files": len(inventory), "jobs": len(rows)}))


if __name__ == "__main__":
    main()
