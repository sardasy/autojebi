"""Versioned section character policy: all text/tail, except v2 field parameters.

One traversal emits text and source ranges. No Unicode normalization is permitted.
Header/footer, notes, drawings, captions, scripts, deleted text and nested tables
remain included when represented as section character nodes (the v1 policy).
"""
from __future__ import annotations

from xml.etree.ElementTree import Element

TEXT_RULE_VERSION = 2
OFFSET_UNIT = "unicode_codepoint"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def section_content(root: Element, locator: str, offset: int = 0,
                    rule_version: int = TEXT_RULE_VERSION) -> dict:
    if rule_version not in {1, 2}:
        raise ValueError("unsupported_text_rule")
    parts: list[str] = []
    spans: list[dict] = []
    excluded: list[dict] = []
    tables: list[dict] = []
    position, visited = 0, 0

    def append(value: str | None, hidden: bool) -> None:
        nonlocal position
        if value and not hidden:
            position += bool(parts) + len(value)
            if position > 200_000:
                raise ValueError("extracted_text_limit")
            parts.append(value)

    def visit(node: Element, path: str, parent: str = "", hidden: bool = False,
              table: dict | None = None, cell: dict | None = None,
              depth: int = 0) -> tuple[bool, list[str]]:
        nonlocal visited
        visited += 1
        if visited > 100_000 or depth > 128:
            raise ValueError("xml_structure_limit")
        start = position + bool(parts)
        local = node.tag.rsplit("}", 1)[-1]
        control = node.tag == HP + "parameters" and parent == HP + "fieldBegin"
        record = None
        if control:
            anchor = offset + (start if rule_version == 1 else position)
            record = {"locator": f"{locator}#xml={path}", "start": anchor,
                      "end": anchor, "text": ""}
            excluded.append(record)
        hide = hidden or (control and rule_version == 2)
        # Record parameter character nodes in the same traversal, including tails.
        control_parts: list[str] = []
        if local == "tbl" and not hide:
            if len(tables) >= 100:
                raise ValueError("table_collection_limit")
            table = {"reference_table_id": node.get("id"), "locator": f"{locator}#xml={path}",
                     "parent_cell": cell["locator"] if cell else None,
                     "rows": node.get("rowCnt"), "cols": node.get("colCnt"),
                     "start": offset + start, "end": offset + start, "cells": []}
            tables.append(table)
            cell = None
        elif local == "tc" and table is not None and not hide:
            cell = {"locator": f"{locator}#xml={path}", "start": offset + start,
                    "end": offset + start, "row": None, "col": None,
                    "row_span": None, "col_span": None}
            table["cells"].append(cell)
        if cell is not None and local in {"cellAddr", "cellSpan"}:
            names = {"rowAddr": "row", "colAddr": "col", "rowSpan": "row_span", "colSpan": "col_span"}
            for name, key in names.items():
                if name in node.attrib:
                    cell[key] = node.get(name)
        append(node.text, hide)
        if node.text:
            control_parts.append(node.text)
        descendant_p = False
        for index, child in enumerate(node):
            child_has_p, child_text = visit(child, f"{path}/{index}", node.tag, hide, table, cell, depth + 1)
            descendant_p |= child_has_p
            control_parts.extend(child_text)
            append(child.tail, hide)
            if child.tail:
                control_parts.append(child.tail)
        end = offset + position
        if record is not None:
            record.update(text=" ".join(control_parts), end=end if rule_version == 1 else record["start"])
        if not hide:
            if local == "tbl" and table is not None:
                table["end"] = end
                table["start"] = min(table["start"], end)
            if local == "tc" and cell is not None:
                cell["end"] = end
                cell["start"] = min(cell["start"], end)
            if (local == "tr" or (local == "p" and not descendant_p)) and end > offset + start:
                spans.append({"start": offset + start, "end": end,
                              "locator": f"{locator}#xml={path}",
                              "kind": "row" if local == "tr" else "paragraph"})
        return local == "p" or descendant_p, control_parts

    visit(root, "0")
    return {"text": " ".join(parts), "spans": spans,
            "excluded": [item for item in excluded if item["text"].strip()], "tables": tables}
