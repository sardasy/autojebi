import json
import subprocess
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.specifications.table_structure import TableStructure
from api.workspace import pdf_text


def page(number, text):
    return SimpleNamespace(page_number=number, extract_text=lambda: text)


def test_mixed_pdf_never_silently_omits_scanned_pages(monkeypatch):
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda *_: nullcontext(SimpleNamespace(pages=[page(1, "native body"), page(2, "")])) )
    monkeypatch.setattr(pdf_text, "ocr_page", lambda *_: {"text": "", "code": "ocr_engine_missing"})
    result = pdf_text.extract_pdf(b"%PDF fake")
    assert result["text"] == "[페이지 1]\nnative body"
    assert not result["extraction"]["complete"]
    assert result["extraction"]["pages"][1]["status"] == "unread"


def test_ocr_text_is_available_but_not_automatically_verified(monkeypatch):
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda *_: nullcontext(SimpleNamespace(pages=[page(1, "")])) )
    monkeypatch.setattr(pdf_text, "ocr_page", lambda *_: {"text": "2 kW", "code": "ocr_review_required", "confidence": 95.5})
    result = pdf_text.extract_pdf(b"%PDF fake")
    assert "2 kW" in result["text"]
    assert not result["extraction"]["complete"]
    assert result["extraction"]["pages"][0]["review_required"]
    assert result["extraction"]["tables"] == []
    assert result["extraction"]["table_structure"]["status"] == "unknown"
    assert not result["extraction"]["table_structure"]["structure_trustworthy"]


def test_tesseract_missing_does_not_call_subprocess(monkeypatch):
    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    monkeypatch.setenv("WORKSPACE_OCR_ENABLED", "true")
    monkeypatch.setattr(pdf_text.shutil, "which", lambda _: None)
    assert pdf_text.ocr_page(None)["code"] == "ocr_engine_missing"


def test_ocr_budget_is_shared_across_documents(monkeypatch):
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda *_: nullcontext(SimpleNamespace(pages=[page(1, "")])))
    calls = []
    monkeypatch.setattr(pdf_text, "ocr_page", lambda *_: calls.append(True) or {"text": "read", "code": "ocr_review_required"})
    budget = [1]
    pdf_text.extract_pdf(b"%PDF fake", ocr_budget=budget)
    second = pdf_text.extract_pdf(b"%PDF fake", ocr_budget=budget)
    assert len(calls) == 1
    assert second["extraction"]["pages"][0]["code"] == "ocr_page_limit"


@pytest.mark.parametrize("timeout", [False, True])
def test_tesseract_is_local_bounded_and_returns_word_confidence(monkeypatch, timeout):
    monkeypatch.setenv("TESSERACT_CMD", "test-tesseract")
    monkeypatch.setenv("WORKSPACE_OCR_ENABLED", "true")
    monkeypatch.setenv("WORKSPACE_OCR_LANGUAGES", "kor+eng")
    class Image:
        def save(self, path):
            path.write_bytes(b"inert fixture")
    source = SimpleNamespace(width=600, height=800, to_image=lambda **_: SimpleNamespace(original=Image()))
    def run(args, **kwargs):
        assert kwargs["timeout"] == 20 and kwargs["shell"] is False
        assert args[-3:] == ["-l", "kor+eng", "tsv"]
        if timeout:
            raise subprocess.TimeoutExpired(args, 20)
        Path(args[2] + ".tsv").write_text("level\tblock_num\tpar_num\tline_num\tconf\ttext\n5\t1\t1\t1\t90\tTest\n5\t1\t1\t1\t100\tOnly\n", encoding="utf-8")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(pdf_text.subprocess, "run", run)
    result = pdf_text.ocr_page(source)
    assert result["code"] == ("ocr_timeout" if timeout else "ocr_review_required")
    if not timeout:
        assert result["text"] == "Test Only" and result["confidence"] == 95.0


def table_page(number=1, *, matching_geometry=True):
    matrix = [["Item", "Voltage (V)"], ["Module", "400"], [None, ""]]
    layout = SimpleNamespace(
        bbox=(0, 0, 200, 60),
        extract=lambda: matrix if matching_geometry else [["Different table"]],
        rows=[SimpleNamespace(cells=[(0, r * 20, 100, r * 20 + 20),
                                     (100, r * 20, 200, r * 20 + 20)]) for r in range(3)],
    )
    return SimpleNamespace(page_number=number, width=600, height=800, images=[],
                           extract_text=lambda: "native body", extract_tables=lambda: [matrix],
                           find_tables=lambda: [layout])


def test_pdf_table_preserves_old_text_metadata_and_empty_cells(monkeypatch):
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda *_: nullcontext(SimpleNamespace(pages=[table_page()])))
    result = pdf_text.extract_pdf(b"%PDF fixture")
    assert result["text"] == "[페이지 1]\nnative body\nItem | Voltage (V)\nModule | 400"
    assert result["extraction"]["complete"]
    assert result["extraction"]["pages"] == [{"page_no": 1, "method": "pdf_text", "review_required": False, "status": "extracted"}]
    table = TableStructure.model_validate(result["extraction"]["tables"][0])
    assert table.needs_review and not table.headers_confirmed
    assert all(not cell.header_paths for cell in table.cells)
    assert table.cells[-1].raw_text == table.cells[-2].raw_text == ""
    assert table.cells[3].source.bbox == (100, 20, 200, 40)
    assert table.cells[3].source.page == 1
    assert result["extraction"]["table_structure"]["source_locations"][0]["page"] == 1
    json.dumps(result, allow_nan=False)


def test_pdf_geometry_mismatch_never_attaches_another_tables_boxes(monkeypatch):
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda *_: nullcontext(SimpleNamespace(pages=[table_page(matching_geometry=False)])))
    table = pdf_text.extract_pdf(b"%PDF fixture")["extraction"]["tables"][0]
    assert all(cell["source"]["bbox"] is None for cell in table["cells"])
    assert table["needs_review"]
    assert "missing_pdf_geometry" in {issue["code"] for issue in table["issues"]}


def test_pdf_repeated_headers_keep_page_specific_locations(monkeypatch):
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda *_: nullcontext(SimpleNamespace(pages=[table_page(1), table_page(2)])))
    tables = pdf_text.extract_pdf(b"%PDF fixture")["extraction"]["tables"]
    assert len(tables) == 2
    assert tables[0]["cells"][0]["raw_text"] == tables[1]["cells"][0]["raw_text"]
    assert tables[0]["cells"][0]["source"]["locator"] != tables[1]["cells"][0]["source"]["locator"]
    assert tables[1]["cells"][0]["source"]["page"] == 2


def test_pdf_no_tables_does_not_create_document_review_flag(monkeypatch):
    source = table_page()
    source.extract_tables = lambda: []
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda *_: nullcontext(SimpleNamespace(pages=[source])))
    result = pdf_text.extract_pdf(b"%PDF fixture")
    assert result["extraction"]["tables"] == []
    assert result["extraction"]["table_structure"]["status"] == "not_detected"
    assert not result["extraction"]["table_structure"]["needs_review"]
    assert result["extraction"]["complete"]


def test_pdf_table_limit_preserves_body_and_records_failure(monkeypatch):
    source = table_page()
    source.extract_tables = lambda: [[list(map(str, range(129)))]]
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda *_: nullcontext(SimpleNamespace(pages=[source])))
    result = pdf_text.extract_pdf(b"%PDF fixture")
    assert result["text"].endswith("127 | 128")
    assert result["extraction"]["complete"]
    assert result["extraction"]["tables"] == []
    assert result["extraction"]["table_structure"]["issues"][0]["code"] == "table_dimension_limit"
