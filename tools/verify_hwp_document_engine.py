"""Opt-in live regression of generate/put-fields using synthetic documents only.

Run: HWP_LIVE_SMOKE=true python -m tools.verify_hwp_document_engine
The authenticated Worker owns every COM operation. Never retries writes, clears
recovery markers, changes registration, or touches an existing output file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from api.hwp_worker.layout import compile_markdown
from api.parsing.hwp_readback import verify_readback
from api.parsing.hwp_validation import read_hwp_output, validate_hwp_content
from api.services.hwp_agent_client import validate_put_fields_response
from api.workspace.hwp_layout import validate_created

BODY = """# TEST ONLY - Document Engine 기능 검증

합성 시험 자료이며 실제 입찰 제출 문서가 아닙니다.

첫 번째 줄입니다.
두 번째 줄입니다.
세 번째 줄입니다.

| 항목 | 시험 값 |
|---|---|
| 수량 | 시험 장비 3대 |
| 납품 | 시험 계약 후 30일 |
| 보증 | 시험 검수 후 24개월 |

<!-- page -->

## 두 번째 페이지

한글과 숫자, 표 셀의 저장값을 검증합니다.

1. 시험용 첫 항목
2. 시험용 둘째 항목

<!-- page -->

## 세 번째 페이지

마지막 첫 줄
마지막 둘째 줄
마지막 셋째 줄
"""


def digest(path: Path) -> str:
    return hashlib.sha256(read_hwp_output(path)).hexdigest()


def save(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def request(client: httpx.Client, folder: Path, label: str, endpoint: str, payload: dict) -> dict:
    print(json.dumps({"stage": label, "state": "started"}), flush=True)
    # httpx has no retry transport; each write is attempted exactly once.
    response = client.post(endpoint, json=payload)
    if response.status_code != 200:
        body = response.json()
        detail = body.get("detail", {}) if isinstance(body, dict) else {}
        code = detail.get("code", "worker_error") if isinstance(detail, dict) else "worker_error"
        if not isinstance(code, str) or not re.fullmatch(r"[a-z_]{1,80}", code):
            code = "worker_error"
        save(folder / f"{label}-error.json", {"status": response.status_code, "code": code})
        raise RuntimeError(code)
    result = response.json()
    save(folder / f"{label}-response.json", result)
    return result


def run(client: httpx.Client, root: Path) -> dict:
    health = client.get("/health").json()
    if (health.get("ok") is not True or health.get("accepting") is not True
            or health.get("recovery_required") is not False
            or health.get("queue", {}).get("running") is not False
            or health.get("queue", {}).get("queued") != 0):
        raise RuntimeError("worker_not_idle_ready")
    if client.post("/document/generate", json={}).status_code != 422:
        raise RuntimeError("generate_route_not_ready")
    operation = "engine-test-" + uuid4().hex
    folder = root / operation
    folder.mkdir()
    print(json.dumps({"folder": str(folder), "purpose": "TEST ONLY"}), flush=True)
    layout, values, manifest = compile_markdown(BODY)
    multiline = [key for key, value in values.items() if "\n" in value]
    values[multiline[-1]] = values[multiline[-1]].replace("\n", "\r\n")
    save(folder / "input.json", {"values": values, "layout": layout.model_dump(),
                                "manifest": manifest, "layout_review": "pending"})
    try:
        template = folder / "working-template.hwp"
        creation = request(client, folder, "create", "/document/create-template", {
            "operation_id": operation + "-create", "output_path": str(template),
            "layout": layout.model_dump(), "visible": False,
        })
        template_hash = validate_created(creation, template, layout, None)
        results = []
        for label, endpoint, suffix in (
            ("generate-hwp", "/document/generate", ".hwp"),
            ("generate-hwpx", "/document/generate", ".hwpx"),
            ("legacy-hwp", "/document/put-fields", ".hwp"),
        ):
            output = folder / (label + suffix)
            raw = request(client, folder, label, endpoint, {
                "template_path": str(template), "output_path": str(output), "values": values,
                "visible": False, "render_pages": True, "operation_id": operation + "-" + label,
            })
            report = validate_put_fields_response(raw, list(values))
            structure = validate_hwp_content(read_hwp_output(output), suffix)
            proof = verify_readback(raw, values, template_hash, digest(output))
            if (not proof or report.missing or report.remaining_placeholders
                    or report.output_path != str(output) or digest(template) != template_hash):
                raise RuntimeError("saved_document_verification_failed")
            pages = raw.get("pages", [])
            if len(pages) != 3:
                raise RuntimeError("expected_three_pages")
            for number, page in enumerate(pages, 1):
                path = Path(page["path"])
                if (page["number"] != number or path.is_symlink() or path.suffix != ".png"
                        or not path.resolve().is_relative_to(folder / (output.stem + "-pages"))
                        or hashlib.sha256(path.read_bytes()).hexdigest() != page["sha256"]
                        or page.get("edge_check") != "passed"):
                    raise RuntimeError("page_verification_failed")
            results.append({"label": label, "output": str(output), "proof": proof,
                            "structure": structure, "sha256": digest(output), "pages": pages})
            print(json.dumps({"stage": label, "verified": True, "fields": len(values),
                              "pages": len(pages)}), flush=True)
        final_health = client.get("/health").json()
        if final_health.get("ok") is not True or final_health.get("recovery_required") is not False:
            raise RuntimeError("worker_not_ready_after_test")
        report = {"purpose": "TEST ONLY", "results": results, "layout_review": "pending",
                  "template_sha256": template_hash, "worker_ready": True}
        save(folder / "verification.json", report)
        return {"verified": True, "folder": str(folder), "outputs": len(results),
                "fields": len(values), "pages": sum(len(item["pages"]) for item in results)}
    except Exception as exc:
        save(folder / "failure.json", {"error_type": type(exc).__name__, "retry_performed": False,
                                      "layout_review": "pending"})
        raise


def main() -> None:
    load_dotenv(override=False)
    if os.getenv("HWP_LIVE_SMOKE") != "true":
        raise SystemExit("Set HWP_LIVE_SMOKE=true to generate new TEST ONLY documents.")
    base = os.getenv("HWP_AGENT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    if urlsplit(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Only the local authenticated Worker is supported.")
    token = os.getenv("HWP_AGENT_TOKEN", "").strip()
    if len(token) < 32:
        raise SystemExit("Worker token is required.")
    root = Path(os.environ["HWP_OUTPUT_ROOT"]).resolve(strict=True)
    with httpx.Client(base_url=base, headers={"X-Agent-Token": token},
                      timeout=httpx.Timeout(120, connect=5), trust_env=False) as client:
        try:
            print(json.dumps(run(client, root)), flush=True)
        except Exception as exc:
            # Native/request exceptions can expose local paths; retain only the type.
            raise SystemExit("Live test failed: " + type(exc).__name__) from None


if __name__ == "__main__":
    main()
