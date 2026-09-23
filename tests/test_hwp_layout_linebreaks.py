"""Whitespace is content, but must not become standalone unfilled Hancom fields."""

import hashlib

import pytest

from api.hwp_worker.com_driver import _remaining
from api.hwp_worker.field_text import wire_text
from api.hwp_worker.layout import compile_markdown
from api.parsing.hwp_readback import verify_readback
from api.parsing.hwp_validation import HwpValidationError


def readback(values):
    fields = [{"field": field, "occurrence": 0} for field in values]
    saved = [{**field, "value": wire_text(values[field["field"]])} for field in fields]
    return {"fields": list(values), "replaced": list(values), "missing": [],
        "remaining_placeholders": _remaining(saved),
        "verification": {"contract_version": 1, "template_sha256": "a" * 64,
            "output_sha256": "b" * 64, "template_fields": fields, "saved_fields": fields,
            "readback": saved, "lifecycle": ["opened", "written", "saved", "closed",
                                             "reopened", "readback", "closed", "quit"]}}


@pytest.mark.parametrize("separator", ["\n", "  \n", "\\\n", "\r\n", "\r"])
def test_soft_and_hard_linebreaks_are_content_not_unfilled_fields(separator):
    text = "첫째 줄" + separator + "둘째 줄"
    layout, values, manifest = compile_markdown(text)
    assert list(values.values()) == ["첫째 줄\n", "둘째 줄"]
    assert layout.fields() == list(values) == [entry["field"] for entry in manifest]
    assert all(entry["text_sha256"] == hashlib.sha256(values[entry["field"]].encode()).hexdigest()
               for entry in manifest)
    raw = readback(values)
    assert raw["remaining_placeholders"] == []
    assert verify_readback(raw, values, "a" * 64, "b" * 64)["verified"] is True
    raw["verification"]["readback"][0]["value"] = "첫째 줄"
    with pytest.raises(HwpValidationError):
        verify_readback(raw, values, "a" * 64, "b" * 64)


def test_styled_runs_links_lists_and_table_cells_keep_text_style_and_updated_hashes():
    body = "**굵게**\n*기울임* [제조사](https://example.com)\n일반\n\n3. **첫째**\n   둘째\n\n| 항목 | 내용 |\n|---|---|\n| **A** *B* | C |"
    layout, values, manifest = compile_markdown(body)
    paragraph = layout.blocks[0]
    assert "".join(values[run.field] for run in paragraph.runs) == "굵게\n기울임 제조사 (https://example.com)\n일반"
    assert values[paragraph.runs[0].field] == "굵게\n" and paragraph.runs[0].bold
    assert values[paragraph.runs[1].field] == "기울임 " and paragraph.runs[1].italic
    assert "".join(values[run.field] for run in layout.blocks[1].runs) == "3. 첫째\n둘째"
    table = layout.blocks[-1]
    assert table.kind == "table"
    assert [["".join(values[run.field] for run in cell) for cell in row] for row in table.rows] == [["항목", "내용"], ["A B", "C"]]
    assert table.rows[1][0][0].bold and table.rows[1][0][1].italic
    assert all(value.strip() for value in values.values())
    assert readback(values)["remaining_placeholders"] == []
    assert all(entry["text_sha256"] == hashlib.sha256(values[entry["field"]].encode()).hexdigest()
               for entry in manifest)
    again = compile_markdown(body)
    assert again[0].checksum() == layout.checksum() and again[1:] == (values, manifest)


def test_leading_explicit_break_belongs_to_next_text_run():
    layout, values, manifest = compile_markdown("\\\n**다음 줄**")
    assert list(values.values()) == ["\n다음 줄"]
    assert layout.blocks[0].runs[0].bold
    assert manifest[0]["text_sha256"] == hashlib.sha256("\n다음 줄".encode()).hexdigest()
    assert readback(values)["remaining_placeholders"] == []


def test_leading_break_does_not_become_part_of_autolink_caption():
    _, values, _ = compile_markdown("\\\n<https://example.com>")
    assert "".join(values.values()) == "\nhttps://example.com"
    assert readback(values)["remaining_placeholders"] == []


def test_actual_empty_table_cells_are_still_unfilled():
    _, values, _ = compile_markdown("| 항목 | 내용 |\n|---|---|\n| A | |")
    empty = [field for field, value in values.items() if not value.strip()]
    assert len(empty) == 1
    assert readback(values)["remaining_placeholders"] == empty
