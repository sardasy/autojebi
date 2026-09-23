"""ID-only table pairing, geometry checks and duplicate-free text ranges."""
from __future__ import annotations

from collections import Counter

from api.parsing.text_diff import Budget, diff_text


def geometry(table: dict) -> tuple:
    return (table["rows"], table["cols"], sorted(
        (c["row"], c["col"], c["row_span"], c["col_span"]) for c in table["cells"]))


def row_text(table: dict) -> str:
    return "\n".join(" | ".join(c["text"] for c in sorted(table["cells"], key=lambda c: c["col"])
                               if c["row"] == row) for row in range(table["rows"]))


def remove_ranges(text: str, ranges: list[tuple[int, int]]) -> str:
    parts, end = [], 0
    for start, stop in sorted(ranges):
        if start > end:
            parts.append(text[end:start])
        end = max(end, stop)
    parts.append(text[end:])
    return "".join(parts)


def normalize_tables(tables: list[dict], text: str) -> list[dict]:
    result = []
    for original in tables:
        table = {**original, "cells": [], "valid": True}
        occupied: set[tuple[int, int]] = set()
        try:
            table["rows"], table["cols"] = int(table["rows"]), int(table["cols"])
            if not 0 < table["rows"] <= 2000 or not 0 < table["cols"] <= 128 or table["rows"]*table["cols"] > 20000:
                raise ValueError("dimensions")
            for source in original["cells"]:
                cell = dict(source)
                for key in ("row", "col", "row_span", "col_span"):
                    cell[key] = int(cell[key])
                r, c, h, w = (cell[k] for k in ("row", "col", "row_span", "col_span"))
                if h == 0 or w == 0:
                    if cell.get("text", "").strip():
                        raise ValueError("covered_cell_text")
                    continue
                if r < 0 or c < 0 or h < 1 or w < 1 or r+h > table["rows"] or c+w > table["cols"]:
                    raise ValueError("cell_geometry")
                points = {(y, x) for y in range(r, r+h) for x in range(c, c+w)}
                if occupied & points:
                    raise ValueError("overlapping_cells")
                occupied |= points
                start, end = cell.get("start"), cell.get("end")
                cell["range_valid"] = type(start) is int and type(end) is int and 0 <= start <= end <= len(text)
                if cell["range_valid"]:
                    raw = text[start:end]
                    if "text" in cell and raw != cell["text"]:
                        cell["range_valid"] = False
                    else:
                        # A nested table is counted only in its own table result.
                        ranges = []
                        for child in tables:
                            if child.get("parent_cell") == cell["locator"]:
                                for nested in child["cells"]:
                                    a, b = nested.get("start"), nested.get("end")
                                    if type(a) is int and type(b) is int and start <= a <= b <= end:
                                        ranges.append((a-start, b-start))
                                    else:
                                        cell["range_valid"] = False
                        cell["text"] = remove_ranges(raw, ranges)
                cell.setdefault("text", "")
                table["cells"].append(cell)
            if len(occupied) != table["rows"]*table["cols"]:
                raise ValueError("incomplete_grid")
        except (ValueError, TypeError, KeyError):
            table["valid"] = False
        result.append(table)
    return result


def compare_tables(left: list[dict], right: list[dict], before: str, after: str,
                   budget: Budget) -> dict:
    left, right = normalize_tables(left, before), normalize_tables(right, after)
    lc = Counter(t.get("reference_table_id") for t in left)
    rc = Counter(t.get("reference_table_id") for t in right)
    items, used, left_ranges, right_ranges = [], set(), [], []

    def safe_pair(table: dict) -> bool:
        key = table.get("reference_table_id")
        target = next((t for t in right if t.get("reference_table_id") == key), None)
        return bool(key and lc[key] == rc[key] == 1 and target and table["valid"] and target["valid"]
                    and all(c["range_valid"] for c in [*table["cells"], *target["cells"]]))

    for table in left:
        key = table.get("reference_table_id")
        target = next((t for t in right if t.get("reference_table_id") == key), None)
        item = {"reference_table_id": key, "locator": table["locator"],
                "parent_cell": table.get("parent_cell"), "status": "unmatched", "cells": []}
        descendants = [t for t in left if (t.get("parent_cell") or "").startswith(table["locator"] + "/")]
        if not safe_pair(table) or any(not safe_pair(t) for t in descendants):
            items.append(item)
            continue
        used.add(key)
        item["status"] = "matched" if geometry(table) == geometry(target) else "structure_changed"
        if item["status"] == "matched":
            by_pos = {(c["row"], c["col"]): c for c in target["cells"]}
            for cell in table["cells"]:
                other = by_pos[cell["row"], cell["col"]]
                if cell["text"] != other["text"]:
                    diff = diff_text(cell["text"], other["text"], budget=budget)
                    item["cells"].append({"row": cell["row"], "col": cell["col"],
                                          "before_text": cell["text"], "after_text": other["text"], **diff})
        else:
            a, b = row_text(table), row_text(target)
            item["row_diff"] = {"before_text": a, "after_text": b, **diff_text(a, b, budget=budget)}
        for t, ranges in ((table, left_ranges), (target, right_ranges)):
            ranges.extend((c["start"], c["end"]) for c in t["cells"])
        items.append(item)
    for table in right:
        if table.get("reference_table_id") not in used and not any(t.get("reference_table_id") == table.get("reference_table_id") for t in left):
            items.append({"reference_table_id": table.get("reference_table_id"), "locator": table["locator"], "status": "unmatched", "cells": []})
    return {"items": items, "before_ranges": left_ranges, "after_ranges": right_ranges}
