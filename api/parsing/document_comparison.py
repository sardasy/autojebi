"""Pure comparison orchestration: accepts a neutral reference, never imports its engine."""
from __future__ import annotations

import json
import re

from api.parsing.attachment_text import extract_hwpx
from api.parsing.comparison_models import ComparisonResult
from api.parsing.hwpx_text import OFFSET_UNIT
from api.parsing.table_diff import compare_tables, remove_ranges
from api.parsing.text_diff import Budget, diff_text

COMPARISON_VERSION = 2


def compare_document(content: bytes, suffix: str, stored: str, reference: dict) -> dict:
    budget = Budget()
    before, after = stored, reference["text"]
    controls, uncertain, tables, basis = [], [], [], "stored"
    if suffix.lower() == ".hwpx":
        old, new = extract_hwpx(content, rule_version=1), extract_hwpx(content, rule_version=2)
        removed = old["extraction"]["excluded_controls"]
        if stored == new["text"]:
            basis = "current_extraction"
        elif stored == old["text"]:
            basis, before, controls = "legacy_extraction", new["text"], removed
        else:
            uncertain = [c["text"] for c in removed]
        if basis != "stored":
            tables = new["extraction"]["comparison_tables"]
        else:
            # Structures alone cannot prove their positions in edited stored text.
            tables = [{**t, "cells": [{**c, "start": None, "end": None} for c in t["cells"]]}
                      for t in new["extraction"]["comparison_tables"]]
        table_result = compare_tables(tables, reference["tables"], before, after, budget)
        before = remove_ranges(before, table_result["before_ranges"])
        after = remove_ranges(after, table_result["after_ranges"])
    else:
        table_result = {"items": []}
        uncertain = re.findall(r"Clickhere[^\r\n]*|HelpState[^\r\n]*", stored)
    diff = diff_text(before, after, budget=budget, uncertain=uncertain)
    # Partial edits of a known command are uncertain too; overlap, not substring deletion.
    for value in set(uncertain):
        start = before.find(value)
        while value and start >= 0:
            if not budget.allow(len(diff["changes"]), 1):
                break
            for change in diff["changes"]:
                if change["before_start"] < start+len(value) and change["before_end"] > start:
                    change["kind"] = "unclassified"
            start = before.find(value, start+len(value))
    budget.allow(0, 0)
    if budget.truncated:
        diff["completion"] = "truncated"
    counts = {kind: sum(c["kind"] == kind for c in diff["changes"])
              for kind in ("content", "whitespace", "unclassified")}
    items = table_result["items"]
    result = {"comparison_version": COMPARISON_VERSION, "offset_unit": OFFSET_UNIT,
              "offset_basis": "comparison_text", "completion": diff["completion"],
              "basis": basis, "before_text": before, "after_text": after,
              "changes": diff["changes"], "controls": controls, "tables": items,
              "summary": {**counts, "control_groups": len(controls),
                          "changed_cells": sum(len(t["cells"]) for t in items),
                          "unmatched_tables": sum(t["status"] == "unmatched" for t in items),
                          "structure_changes": sum(t["status"] == "structure_changed" for t in items),
                          "cells_not_compared": suffix.lower() == ".hwp"},
              "has_baseline": bool(stored.strip()), "verified": False}
    if len(json.dumps(result, ensure_ascii=False).encode()) > 1_000_000:
        result.update(completion="truncated", changes=[], tables=[], controls=[], before_text="", after_text="")
        result["truncation_reason"] = "detail_output_limit"
    elif budget.truncated:
        result["truncation_reason"] = "comparison_work_limit"
    return ComparisonResult.model_validate(result).model_dump(exclude_none=True)
