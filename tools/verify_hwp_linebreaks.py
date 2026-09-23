"""Opt-in real Hancom rehearsal through the authenticated Worker, with synthetic data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from api.hwp_worker.field_text import normalize
from api.hwp_worker.layout import compile_markdown
from api.parsing.hwp_readback import verify_readback
from api.services.hwp_agent_client import HwpAgentClient
from api.workspace.hwp_layout import validate_created


def main() -> None:
    load_dotenv(override=False)
    if os.getenv("HWP_LIVE_SMOKE") != "true":
        raise SystemExit("Set HWP_LIVE_SMOKE=true to generate a new TEST ONLY document.")
    root = Path(os.environ["HWP_OUTPUT_ROOT"]).resolve(strict=True)
    operation = "linebreaks-" + uuid4().hex
    folder = root / operation
    folder.mkdir()
    body = (
        "# TEST ONLY - 한글 줄바꿈 검증\n\n"
        "첫 번째 줄입니다.\n두 번째 줄입니다.\n세 번째 줄입니다.\n\n"
        "**합성 시험 자료**입니다. 실제 입찰 제출 문서가 아닙니다.\n\n"
        "| 항목 | 시험 조건 |\n|---|---|\n"
        "| 수량 | 시험 장비 3대 |\n| 납품 | 시험 계약 후 30일 |\n"
        "| 보증 | 시험 검수 후 24개월 |\n\n"
        "<!-- page -->\n\n## 두 번째 페이지\n\n"
        "한글 문장과 숫자·단위의 저장값 및 줄바꿈을 대조합니다.\n\n"
        "1. 시험용 첫 번째 항목\n2. 시험용 두 번째 항목\n\n"
        "<!-- page -->\n\n## 세 번째 페이지\n\n"
        "마지막 첫 줄\n마지막 둘째 줄\n마지막 셋째 줄"
    )
    layout, values, manifest = compile_markdown(body)
    # Exercise both source newline conventions in the same saved document.
    multiline = [key for key, value in values.items() if "\n" in value]
    if len(multiline) < 2:
        raise ValueError("Fixture must include two multiline fields")
    values[multiline[-1]] = values[multiline[-1]].replace("\n", "\r\n")
    worker = HwpAgentClient(retries=1, timeout_s=120)
    if not worker.diagnostics()["available"]:
        raise RuntimeError("Worker unavailable; no recovery state is changed by this tool")
    template, output = folder / "working-template.hwp", folder / "draft.hwp"
    creation = worker.create_template(
        operation_id=operation, output_path=str(template), layout=layout.model_dump(),
    )
    checksum = validate_created(creation, template, layout, None)
    result = worker.put_fields(
        template_path=str(template), output_path=str(output), values=values,
        operation_id=operation + "-fill", render_pages=True,
    )
    (folder / "attempt.json").write_text(json.dumps(
        {"purpose": "TEST ONLY", "creation": creation, "input_values": values,
         "worker": result.raw, "layout_review": "pending"}, ensure_ascii=False, indent=2,
    ), encoding="utf-8")
    output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    proof = verify_readback(result.raw, values, checksum, output_hash)
    if not proof or result.missing or result.remaining_placeholders:
        raise RuntimeError(f"Saved-field verification failed; inspect {folder / 'attempt.json'}")
    if hashlib.sha256(template.read_bytes()).hexdigest() != checksum:
        raise RuntimeError("Template was changed")
    readback = {item["field"]: item["value"] for item in result.raw["verification"]["readback"]}
    lines = [{"field": key, "expected": normalize(values[key]).count("\n"),
              "actual": normalize(readback[key]).count("\n")} for key in multiline]
    if any(item["expected"] != item["actual"] for item in lines):
        raise RuntimeError("Paragraph boundaries were lost")
    pages = result.raw.get("pages") or []
    if len(pages) != 3:
        raise RuntimeError("Expected three rendered pages")
    for number, page in enumerate(pages, 1):
        path = Path(page["path"])
        if (page["number"] != number or path.is_symlink()
                or not path.resolve().is_relative_to(folder / "draft-pages")
                or hashlib.sha256(path.read_bytes()).hexdigest() != page["sha256"]):
            raise RuntimeError("Rendered-page verification failed")
    report = {"purpose": "TEST ONLY", "output": str(output), "sha256": output_hash,
              "proof": proof, "linebreaks": lines, "pages": pages,
              "input_values": values, "body_manifest": manifest,
              "creation": creation, "worker": result.raw, "layout_review": "pending"}
    (folder / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(json.dumps({"folder": str(folder), "fields": len(values),
                      "linebreaks": lines, "pages": len(pages), "verified": True}))


if __name__ == "__main__":
    main()
