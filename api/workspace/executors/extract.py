"""Text extraction job: PDF/HWPX/XLSX/ZIP locally, HWP (OLE) through the Worker."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from api.parsing import attachment_text, pdf_text
from api.parsing.hwp_validation import (
    HwpValidationError,
    read_hwp_output,
)
from api.parsing.hwpx_text import TEXT_RULE_VERSION
from api.services.hwp_agent_client import (
    HwpAgentClient,
    HwpAgentError,
)
from api.workspace.errors import fail
from api.workspace.storage import source_path, storage_root


def extract_archive_hwp(content: bytes, locator: str) -> dict:
    """Keep an immutable, digest-named member in the Worker's allowed source root."""
    if not os.getenv("HWP_AGENT_TOKEN", "").strip():
        raise attachment_text.ArchiveMemberError("hwp_worker_auth_missing")
    if not content or len(content) > attachment_text.MAX_BYTES:
        raise attachment_text.ExtractionError("archive_size_limit")
    root = storage_root()
    folder = (root / "uploads" / "archive-members").resolve()
    if not folder.is_relative_to(root):
        raise attachment_text.ArchiveMemberError("hwp_member_storage_unsafe")
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()
    path = folder / f"{digest}.hwp"
    try:
        with path.open("xb") as target:
            target.write(content)
    except FileExistsError:
        pass
    try:
        if hashlib.sha256(read_hwp_output(path)).hexdigest() != digest:
            raise attachment_text.ArchiveMemberError("hwp_member_source_changed")
    except HwpValidationError:
        raise attachment_text.ArchiveMemberError("hwp_member_source_changed") from None
    try:
        body = HwpAgentClient(retries=1).analyze_document(str(path))
    except HwpAgentError:
        raise attachment_text.ArchiveMemberError("hwp_worker_unavailable") from None
    try:
        if hashlib.sha256(read_hwp_output(path)).hexdigest() != digest:
            raise attachment_text.ArchiveMemberError("hwp_member_source_changed")
    except HwpValidationError:
        raise attachment_text.ArchiveMemberError("hwp_member_source_changed") from None
    text = str(body.get("text") or body.get("extracted_text") or "")
    if len(text) > attachment_text.MAX_TEXT:
        raise attachment_text.ExtractionError("extracted_text_limit")
    return {"text": text, "format": "hwp_ole", "extraction": {
        "version": 1, "complete": bool(text.strip()),
        **attachment_text.text_only_table_metadata(locator=locator, table_count=body.get("table_count")),
    }}


def extract(job: dict) -> dict:
    if not job["snapshot"]["documents"]:
        fail(
            "no_source_files",
            "본문을 추출할 등록 파일이 없습니다.",
            "첨부 가져오기 후 결과 반영을 실행하거나 원문 파일을 등록하세요.",
        )
    texts, warnings = [], []
    ocr_budget = [10]
    hwp_budget = [10]
    for doc in job["snapshot"]["documents"]:
        if doc.get("text_origin") == "manual_confirmed":
            item = {"id": doc["id"], "text": doc["text"], "format": "manual_confirmed"}
            if "extraction" in doc:
                item["extraction"] = doc["extraction"]
            texts.append(item)
            continue
        path = source_path(doc)
        display_name = doc.get("name") or path.name
        metadata = doc.get("extraction") or {}
        if (doc.get("sha256") and doc.get("text") and doc.get("text_origin") == "pdf"
            and metadata.get("version") == 1 and metadata.get("complete") is True):
            if metadata.get("table_structure", {}).get("version") != 1 or "tables" not in metadata:
                try:
                    enriched = pdf_text.extract_pdf(path.read_bytes(), ocr_budget=ocr_budget)["extraction"]
                    addition = {key: enriched[key] for key in ("tables", "table_structure")}
                except Exception:
                    addition = attachment_text.text_only_table_metadata(locator=f"sha256:{doc['sha256']}/pdf")
                metadata = {**metadata, **addition}
            texts.append({"id": doc["id"], "text": doc["text"], "format": "pdf", "extraction": metadata})
            continue
        if (doc.get("sha256") and doc.get("text") and doc.get("text_origin") in {"hwpx", "hwp_ole"}
            and (doc["text_origin"] == "hwp_ole" or
                 metadata.get("text_rule_version") == TEXT_RULE_VERSION and metadata.get("complete") is True)):
            if metadata.get("table_structure", {}).get("version") != 1 or "tables" not in metadata:
                addition = attachment_text.text_only_table_metadata(locator=f"sha256:{doc['sha256']}/{doc['text_origin']}")
                if (doc["text_origin"] == "hwpx" and path.suffix.lower() == ".hwpx"
                    and Path(doc.get("name") or "").suffix.lower() == ".hwpx"):
                    try:
                        enriched = attachment_text.extract_hwpx(path.read_bytes())["extraction"]
                        addition = {key: enriched[key] for key in ("tables", "table_structure")}
                    except Exception:
                        pass
                metadata = {**metadata, **addition}
            texts.append({"id": doc["id"], "text": doc["text"], "format": doc["text_origin"],
                          "extraction": metadata})
            continue
        header = path.read_bytes()[:8]
        try:
            suffix = path.suffix.lower()
            if suffix in {".xlsx", ".zip"} and Path(doc.get("name") or path.name).suffix.lower() == suffix and header.startswith(b"PK"):
                extracted = attachment_text.extract_xlsx(path.read_bytes()) if suffix == ".xlsx" else attachment_text.extract_zip(
                    path.read_bytes(), ocr_budget=ocr_budget,
                    hwp_extractor=extract_archive_hwp, hwp_budget=hwp_budget,
                )
                texts.append({"id": doc["id"], **extracted})
                if not extracted["extraction"]["complete"]:
                    warnings.append(f"{display_name}: 일부 본문 또는 수식 값 확인이 필요합니다. 추출 내역을 확인하세요.")
                continue
            if header.startswith(b"%PDF"):
                extracted = pdf_text.extract_pdf(path.read_bytes(), ocr_budget=ocr_budget)
                texts.append({"id": doc["id"], **extracted})
                if not extracted["extraction"]["complete"]:
                    warnings.append(f"{display_name}: 미추출 또는 OCR 대조 필요 페이지가 있습니다.")
                continue
            elif (
                header.startswith(b"PK")
                and path.suffix.lower() == ".hwpx"
                and Path(doc.get("name") or "").suffix.lower() == ".hwpx"
            ):
                extracted = attachment_text.extract_hwpx(path.read_bytes())
                text = extracted["text"]
                metadata = {**metadata, **extracted["extraction"]}
                fmt = "hwpx"
            elif (
                header.startswith(bytes.fromhex("d0cf11e0a1b11ae1"))
                and path.suffix.lower() == ".hwp"
                and Path(doc.get("name") or path.name).suffix.lower() == ".hwp"
            ):
                if not os.getenv("HWP_AGENT_TOKEN", "").strip():
                    raise ValueError("HWP Worker 인증 설정 필요")
                body = HwpAgentClient(retries=1).analyze_document(str(path))
                text = str(body.get("text") or body.get("extracted_text") or "")
                fmt = "hwp_ole"
                metadata = {**metadata, **attachment_text.text_only_table_metadata(
                    locator=f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}/hwp",
                    table_count=body.get("table_count"),
                )}
            else:
                raise ValueError("본문 추출을 지원하지 않는 형식")
            if not text.strip():
                raise ValueError("본문 추출 결과 없음")
            texts.append({"id": doc["id"], "text": text, "format": fmt, "extraction": metadata})
        except Exception:
            warnings.append(f"{display_name}: 본문 분석 불가. Worker 연결 또는 변환본을 확인하세요.")
    if not texts:
        fail(
            "no_extracted_text",
            "원문 본문을 추출하지 못했습니다.",
            "Worker 연결 또는 확인된 본문 등록이 필요합니다.",
        )
    return {"documents": texts, "warnings": warnings}
