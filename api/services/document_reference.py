"""Boundary adapter: third-party block names never enter the comparison contract."""
from __future__ import annotations

from api.services import kordoc_client

REFERENCE_ENGINE_VERSION = "4.14.1"


def reference_document(content: bytes, suffix: str) -> dict:
    parsed = kordoc_client.parse_document(content, suffix)
    return adapt_reference(parsed.model_dump())


def adapt_reference(parsed: dict) -> dict:
    text = parsed["text"]
    positions, cursor = {}, 0
    # Mirrors the adapter's buffer emission, never a global fuzzy text search.
    primary = [f for f in parsed["fragments"] if (
        f["kind"] == "table_cell" and "/cells/" not in f["table_locator"]
        or f["kind"] == "paragraph" and "/cells/" not in f["locator"])]
    exact = "\n".join(f["text"] for f in primary) == text
    for f in primary:
        if exact:
            positions[f["locator"]] = (cursor, cursor + len(f["text"]))
        cursor += len(f["text"]) + 1
    tables = []
    for t in parsed["tables"]:
        cells = []
        for f in parsed["fragments"]:
            if f.get("table_locator") != t["locator"]:
                continue
            bounds = positions.get(f["locator"])
            # Nested cells can only be located within a known parent cell uniquely.
            if bounds is None and "/cells/" in t["locator"] and f["text"]:
                parents = [(key, value) for key, value in positions.items()
                           if t["locator"].startswith(key + "/")]
                if parents:
                    _, (start, end) = max(parents, key=lambda item: len(item[0]))
                    part = text[start:end]
                    if part.count(f["text"]) == 1:
                        at = start + part.index(f["text"])
                        bounds = (at, at + len(f["text"]))
                        positions[f["locator"]] = bounds
            cells.append({"locator": f["locator"], "row": f["row"], "col": f["col"],
                          "row_span": f["row_span"], "col_span": f["col_span"],
                          "text": f["text"], "start": bounds[0] if bounds else None,
                          "end": bounds[1] if bounds else None})
        tables.append({"reference_table_id": t.get("source_id"), "locator": t["locator"],
                       "rows": t["rows"], "cols": t["cols"], "cells": cells,
                       "parent_cell": t["locator"].rsplit("/blocks/", 1)[0] if "/cells/" in t["locator"] else None})
    return {"text": text, "tables": tables, "page_mode": parsed["page_mode"],
            "warnings": parsed["warnings"], "engine_version": parsed["engine_version"],
            "source_sha256": parsed["source_sha256"], "offset_unit": "unicode_codepoint"}
