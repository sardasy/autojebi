"""Read-only comparison against snapshot text; results cannot be applied or approved."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from api.parsing.document_comparison import compare_document
from api.parsing.hwp_validation import HwpValidationError, read_hwp_output
from api.services import kordoc_client
from api.services.document_reference import REFERENCE_ENGINE_VERSION, reference_document
from api.workspace.errors import WorkspaceError, fail
from api.workspace.storage import source_path


def require_enabled() -> None:
    if not kordoc_client.enabled():
        fail("kordoc_disabled", "문서 추출 비교는 검증 설정을 활성화한 뒤 사용할 수 있습니다.", status=503)


def compare(job: dict) -> dict:
    require_enabled()
    comparisons, total = [], 0
    # Public notice sources only; company/reference evidence is outside this pilot.
    documents = [doc for doc in job["snapshot"]["documents"] if doc.get("role") == "notice_source"]
    if len(documents) > 10:
        fail("comparison_document_limit", "공고 원문 10개 이하인 검증 공고에서 실행하세요.")
    for doc in documents:
        item = {"document_id": doc["id"], "name": doc.get("name", ""),
                "input_version": job["input_version"], "status": "skipped"}
        suffix = Path(doc.get("name", "")).suffix.lower()
        if suffix not in {".hwp", ".hwpx"}:
            comparisons.append({**item, "error_code": "unsupported_format"})
            continue
        try:
            # Check the allowlisted path first; hash only after the bounded read below.
            path = source_path({**doc, "sha256": None})
            content = read_hwp_output(path)
            checksum = hashlib.sha256(content).hexdigest()
            if not doc.get("sha256") or doc["sha256"] != checksum:
                raise kordoc_client.KordocError("source_hash_mismatch")
            candidate = reference_document(content, suffix)
            if hashlib.sha256(read_hwp_output(path)).hexdigest() != checksum:
                raise kordoc_client.KordocError("source_changed")
            baseline = doc.get("text") or ""
            item.update(status="compared", source_sha256=checksum, baseline_text=baseline,
                        reference=candidate, comparison_v2=compare_document(content, suffix, baseline, candidate))
        except kordoc_client.KordocError as exc:
            item.update(status="failed", error_code=str(exc))
        except WorkspaceError as exc:
            item.update(status="failed", error_code=exc.detail["code"])
        except (ValueError, OSError, HwpValidationError):
            item.update(status="failed", error_code="source_unavailable")
        size = len(json.dumps(item, ensure_ascii=False).encode())
        if total + size > 7_950_000 and "comparison_v2" in item:
            item["comparison_v2"].update(completion="truncated", truncation_reason="job_output_limit",
                                         changes=[], controls=[], tables=[], before_text="", after_text="")
            item.pop("reference", None)
            item.pop("baseline_text", None)
            size = len(json.dumps(item, ensure_ascii=False).encode())
        total += size
        comparisons.append(item)
    return {"engine_version": REFERENCE_ENGINE_VERSION, "comparisons": comparisons, "verified": False,
            "warnings": ["추출 비교 결과입니다. 원문·요구사항·검토 승인은 변경되지 않습니다."],
            "review_required": True}
