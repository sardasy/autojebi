"""Page-complete PDF extraction with local, bounded, optional Tesseract OCR."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pdfplumber

from api.specifications.table_structure import (
    SourceLocator,
    TableCell,
    TableLimits,
    TableStructureError,
    table_from_pdf_cells,
)
from api.workspace.attachment_text import (
    MAX_BYTES,
    MAX_TABLES,
    MAX_TEXT,
    ExtractionError,
    TableCollector,
)


def _pdf_tables(page: Any, matrices: list, collector: TableCollector, locator: str) -> None:
    """Keep unconfirmed PDF cells; geometry must match the same extracted matrix."""
    try:
        geometry = page.find_tables() if matrices else []
    except Exception:
        geometry = []
    limits = TableLimits()
    for index, matrix in enumerate(matrices):
        collector.detected += 1
        source = SourceLocator(locator=f"{locator}#page={page.page_number}/table={index}",
                               page=page.page_number)
        try:
            if collector.detected > MAX_TABLES:
                raise TableStructureError("table_collection_limit")
            rows, cols = len(matrix), max((len(row) for row in matrix), default=0)
            if not rows or not cols or rows > limits.max_rows or cols > limits.max_cols or rows * cols > limits.max_cells:
                raise TableStructureError("table_dimension_limit")
            layout = None
            if index < len(geometry):
                candidate = geometry[index]
                if candidate.extract() == matrix:
                    layout = candidate
            cells, text_size = [], 0
            for row, values in enumerate(matrix):
                for col, value in enumerate(values):
                    raw = "" if value is None else str(value)
                    text_size += len(raw)
                    if text_size > limits.max_text_chars:
                        raise TableStructureError("table_text_limit")
                    bbox = None
                    if layout is not None and row < len(layout.rows) and col < len(layout.rows[row].cells):
                        bbox = layout.rows[row].cells[col]
                    cells.append(TableCell(row=row, col=col, raw_text=raw,
                        source=SourceLocator(locator=f"{source.locator}/r={row};c={col}",
                                             page=page.page_number, bbox=bbox)))
            table = table_from_pdf_cells(cells, locator=source.locator, n_rows=rows, n_cols=cols,
                                         row_label_col=None, headers_confirmed=False)
            table = table.model_copy(update={"source": SourceLocator(
                locator=source.locator, page=page.page_number,
                bbox=layout.bbox if layout is not None else None)})
            collector.add(table)
        except TableStructureError as exc:
            collector.reject(str(exc), source)
        except Exception:
            collector.reject("pdf_table_structure_unavailable", source)


def ocr_page(page: Any) -> dict:
    if os.getenv("WORKSPACE_OCR_ENABLED", "true").lower() not in {"true", "1"}:
        return {"text": "", "code": "ocr_disabled"}
    executable = os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
    languages = os.getenv("WORKSPACE_OCR_LANGUAGES", "kor+eng")
    if not executable:
        return {"text": "", "code": "ocr_engine_missing"}
    if not re.fullmatch(r"[a-zA-Z0-9_+]{1,80}", languages):
        return {"text": "", "code": "ocr_configuration_invalid"}
    with tempfile.TemporaryDirectory(prefix="autojebi-ocr-") as folder:
        root = Path(folder)
        image = page.to_image(resolution=min(200, 2400 * 72 / max(page.width, page.height)))
        image.original.save(root / "page.png")
        try:
            with (root / "diagnostic.log").open("wb") as diagnostic:
                result = subprocess.run(
                    [executable, str(root / "page.png"), str(root / "result"), "-l", languages, "tsv"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=diagnostic,
                    timeout=20, check=False, shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
        except subprocess.TimeoutExpired:
            return {"text": "", "code": "ocr_timeout"}
        except OSError:
            return {"text": "", "code": "ocr_engine_unavailable"}
        with (root / "diagnostic.log").open("rb") as diagnostic:
            # Tesseract may exit successfully after silently dropping a requested
            # language or a model dependency. Keep partial text for review, while
            # surfacing the actual setup problem instead of a high-confidence pass.
            message = diagnostic.read(100_000).decode("utf-8", errors="replace")
        missing = sorted(set(re.findall(r"Failed loading language '([a-zA-Z0-9_]{1,80})'", message)))
        language_issue = {"missing_languages": missing} if missing else {}
        output = root / "result.tsv"
        if result.returncode != 0 or not output.is_file():
            return {"text": "", "code": "ocr_language_missing" if missing else "ocr_failed",
                    **language_issue}
        if output.stat().st_size > 5_000_000:
            return {"text": "", "code": "ocr_output_limit"}
        lines, confidences, previous = [], [], None
        with output.open(encoding="utf-8") as stream:
            for item in csv.DictReader(stream, delimiter="\t"):
                if item.get("level") != "5" or not item.get("text", "").strip():
                    continue
                confidence = float(item["conf"])
                if not 0 <= confidence <= 100:
                    continue
                key = tuple(item[k] for k in ("block_num", "par_num", "line_num"))
                if key != previous:
                    lines.append([])
                    previous = key
                lines[-1].append(item["text"])
                confidences.append(confidence)
        text = "\n".join(" ".join(line) for line in lines)
        if len(text) > MAX_TEXT:
            return {"text": "", "code": "ocr_output_limit"}
        return {"text": text, "code": "ocr_language_missing" if missing else "ocr_review_required",
                "engine": "tesseract", **language_issue,
                "languages": languages, "confidence": round(sum(confidences) / len(confidences), 2) if confidences else None}


def extract_pdf(content: bytes, *, ocr_budget: list[int] | None = None,
                locator: str | None = None) -> dict:
    if len(content) > MAX_BYTES:
        raise ExtractionError("pdf_size_limit")
    pages, texts, length = [], [], 0
    locator = locator or f"sha256:{hashlib.sha256(content).hexdigest()}/pdf"
    tables = TableCollector()
    ocr_budget = [10] if ocr_budget is None else ocr_budget
    with pdfplumber.open(io.BytesIO(content)) as document:
        if len(document.pages) > 100:
            raise ExtractionError("pdf_page_limit")
        for page in document.pages:
            record = {"page_no": page.page_number, "method": "pdf_text", "review_required": False}
            text = page.extract_text() or ""
            needs_ocr = not text.strip()
            if not needs_ocr and len(text.strip()) < 200:
                needs_ocr = any(image.get("width", 0) * image.get("height", 0) > page.width * page.height / 2
                                for image in getattr(page, "images", []))
            if not needs_ocr:
                try:
                    matrices = page.extract_tables() or []
                    for table in matrices:
                        for row in table:
                            cells = [str(cell).strip() for cell in row if cell and str(cell).strip()]
                            if cells:
                                text += "\n" + " | ".join(cells)
                    _pdf_tables(page, matrices, tables, locator)
                except Exception:
                    tables.unknown = True
            if needs_ocr:
                # OCR word text provides neither table presence nor cell geometry.
                tables.unknown = True
                if ocr_budget[0] <= 0:
                    result = {"text": "", "code": "ocr_page_limit"}
                else:
                    ocr_budget[0] -= 1
                    try:
                        result = ocr_page(page)
                    except Exception:
                        result = {"text": "", "code": "ocr_failed"}
                ocr_text = result.pop("text")
                text = "\n".join(part for part in (text, ocr_text) if part.strip())
                record.update(method="ocr", review_required=True, **result)
            record["status"] = "extracted" if text.strip() else "unread"
            pages.append(record)
            if text.strip():
                block = f"[페이지 {page.page_number}]\n{text}"
                length += len(block) + 1
                if length > MAX_TEXT:
                    raise ExtractionError("extracted_text_limit")
                texts.append(block)
    return {"text": "\n".join(texts), "format": "pdf", "extraction": {
        "version": 1, "pages": pages,
        "complete": bool(pages) and all(p["status"] == "extracted" and not p["review_required"] for p in pages),
        **tables.metadata(),
    }}
