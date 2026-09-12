"""Layout authoring on the Worker's COM owner thread, never a second COM host."""
from __future__ import annotations

from pathlib import Path

from api.hwp_worker.com_driver import (
    ComDriverError,
    _call,
    _digest,
    _operation,
    _refuse_existing_output,
    _success,
    _void,
)
from api.hwp_worker.layout import Layout, Run


def action(hwp, name: str, values: dict | None = None, *, phase="layout", configure=None):
    act = _call(phase, hwp.CreateAction, name)
    params = _call(phase, act.CreateSet)
    _call(phase, act.GetDefault, params)
    for key, value in (values or {}).items():
        _call(phase, params.SetItem, key, value)
    if configure:
        configure(params)
    if not _success(_call(phase, act.Execute, params)):
        raise ComDriverError("action_failed", phase)


def run(hwp, name: str, phase="layout"):
    _void(phase, hwp.HAction.Run, name)


def create_template(base: Path | None, output: Path, layout: Layout, visible: bool) -> dict:
    _refuse_existing_output(output)
    base_hash = _digest(base, "template_hash") if base else None
    with _operation(visible) as session:
        hwp = session.hwp
        if base:
            session.open(base)
            if session.enumerate() != [{"field": "proposal_body", "occurrence": 0}]:
                raise ComDriverError("layout_base_must_have_body_anchor_only", "document")
            run(hwp, "SelectAll", "document")
            run(hwp, "Delete", "document")
        else:
            run(hwp, "FileNew", "document")
            count = _call("document", lambda: hwp.XHwpDocuments.Count)
            if type(count) is not int or count < 1:
                raise ComDriverError("active_document_missing", "document")
            session.opened = True
            session.lifecycle.append("created")

        def page_setup(params):
            page = _call("page_setup", params.Item, "PageDef")
            for key, value in {"PaperWidth": 59528, "PaperHeight": 84188, "Landscape": 0,
                               "LeftMargin": 5669, "RightMargin": 5669, "TopMargin": 5669,
                               "BottomMargin": 5669, "HeaderLen": 2835, "FooterLen": 2835}.items():
                _call("page_setup", page.SetItem, key, value)
            _call("page_setup", params.SetItem, "PageDef", page)
        action(hwp, "PageSetup", phase="page_setup", configure=page_setup)

        def field(item: Run, size: int, header=False):
            action(hwp, "CharShape", {"Height": size, "FaceNameHangul": "맑은 고딕",
                   "FaceNameLatin": "맑은 고딕", "Bold": int(item.bold or header),
                   "Italic": int(item.italic)}, phase="font")
            if not _success(_call("field", hwp.CreateField, "", "", item.field)):
                raise ComDriverError("field_create_failed", "field")
            if not _success(_call("field", hwp.MoveToField, item.field, False, False, False)):
                raise ComDriverError("field_position_failed", "field")

        for block in layout.blocks:
            if block.kind == "page_break":
                run(hwp, "BreakPage")
            elif block.kind == "table":
                cols = len(block.rows[0])
                def table_setup(params, cols=cols):
                    props = _call("table", params.Item, "TableProperties")
                    for key, value in {"TreatAsChar": 0, "RepeatHeader": 1, "PageBreak": 2,
                                       "TextWrap": 1, "HorzAlign": 0, "HorzOffset": 0}.items():
                        _call("table", props.SetItem, key, value)
                    _call("table", params.SetItem, "TableProperties", props)
                action(hwp, "TableCreate", {"Rows": len(block.rows), "Cols": cols,
                       "WidthType": 0, "HeightType": 0}, phase="table", configure=table_setup)
                for row_index, row in enumerate(block.rows):
                    for col_index, cell in enumerate(row):
                        for item in cell:
                            field(item, 950, header=row_index == 0)
                        if (row_index, col_index) != (len(block.rows) - 1, cols - 1):
                            run(hwp, "TableRightCell", "table")
                run(hwp, "CloseEx", "table")
                run(hwp, "MoveDocEnd", "table")
                run(hwp, "BreakPara", "table")
            else:
                action(hwp, "ParagraphShape", {"LineSpacing": 155, "LineSpacingType": 0}, phase="paragraph")
                size = (1800 if block.level == 1 else 1300) if block.kind == "heading" else 1050
                for item in block.runs:
                    field(item, size, header=block.kind == "heading")
                run(hwp, "BreakPara")

        expected = [{"field": name, "occurrence": 0} for name in layout.fields()]
        if session.enumerate() != expected:
            raise ComDriverError("layout_fields_mismatch", "verify")
        # Page numbering is a document-local control, not a system preference.
        action(hwp, "PageNumPos", {"DrawPos": 5}, phase="page_number")
        _refuse_existing_output(output)
        if not _success(_call("save", hwp.SaveAs, str(output), "HWP", "")):
            raise ComDriverError("document_save_failed", "save")
        session.lifecycle.append("saved")
        session.close()
        checksum = _digest(output, "output_hash")
        session.open(output, reopen=True)
        if session.enumerate() != expected:
            raise ComDriverError("saved_fields_mismatch", "verify")
        session.close()
        if _digest(output, "output_hash") != checksum or (base and _digest(base, "template_hash") != base_hash):
            raise ComDriverError("template_changed", "verify")
        result = {"output_path": str(output), "sha256": checksum, "base_sha256": base_hash,
                  "layout_sha256": layout.checksum(), "fields": layout.fields(),
                  "field_occurrences": expected, "lifecycle": session.lifecycle}
    return result
