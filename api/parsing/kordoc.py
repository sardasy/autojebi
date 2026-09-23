"""Bounded candidate structure and comparison metrics, never accepted source quotes."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE_VERSION = "4.14.1"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Fragment(Model):
    locator: str = Field(pattern=r"^blocks/[0-9]+(?:/[A-Za-z0-9_]+)*$", max_length=1000)
    kind: Literal["paragraph", "table_cell"]
    text: str = Field(max_length=200_000)
    page: int | None = Field(default=None, ge=1, le=10000)
    table_locator: str | None = Field(default=None, max_length=1000)
    row: int | None = Field(default=None, ge=0, lt=2000)
    col: int | None = Field(default=None, ge=0, lt=128)
    row_span: int | None = Field(default=None, ge=0, le=2000)
    col_span: int | None = Field(default=None, ge=0, le=128)


class Table(Model):
    locator: str = Field(max_length=1000)
    rows: int = Field(ge=1, le=2000)
    cols: int = Field(ge=1, le=128)
    source_id: str | None = Field(default=None, max_length=200)
    page: int | None = Field(default=None, ge=1, le=10000)


class ParsedDocument(Model):
    contract_version: Literal[1]
    engine_version: Literal["4.14.1"]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    format: Literal["hwp", "hwpx"]
    page_mode: Literal["layout", "section", "unknown"]
    text: str = Field(max_length=200_000)
    markdown: str = Field(max_length=200_000)
    fragments: list[Fragment] = Field(max_length=20_000)
    tables: list[Table] = Field(max_length=100)
    warnings: list[str] = Field(max_length=100)
    review_required: Literal[True]
    verified: Literal[False]

    @model_validator(mode="after")
    def consistency(self) -> ParsedDocument:
        if sum(len(item.text) for item in self.fragments) > 1_000_000:
            raise ValueError("fragment_limit")
        if len({item.locator for item in self.fragments}) != len(self.fragments):
            raise ValueError("duplicate_locator")
        if self.page_mode != "layout" and any(item.page for item in [*self.fragments, *self.tables]):
            raise ValueError("approximate_page_cannot_be_citation")
        tables = {table.locator: table for table in self.tables}
        if len(tables) != len(self.tables) or any(t.rows * t.cols > 20_000 for t in self.tables):
            raise ValueError("invalid_tables")
        for item in self.fragments:
            if item.kind == "table_cell":
                table = tables.get(item.table_locator)
                if (table is None or item.row is None or item.col is None
                        or item.row_span is None or item.col_span is None
                        or item.row >= table.rows or item.col >= table.cols
                        or item.row + item.row_span > table.rows
                        or item.col + item.col_span > table.cols):
                    raise ValueError("invalid_cell")
        if any(not re.fullmatch(r"[A-Z_]{1,80}", code) for code in self.warnings):
            raise ValueError("invalid_warning_code")
        if {"COM_EMPTY", "DRM_COM_FALLBACK"} & set(self.warnings):
            raise ValueError("com_result_rejected")
        return self


def compare_text(baseline: str, candidate: str) -> dict:
    """Token differences are review hints, not accuracy or factuality scores."""
    if len(baseline) > 200_000 or len(candidate) > 200_000:
        raise ValueError("text_limit")
    before = Counter(re.findall(r"[\w]+(?:[.,][0-9]+)*", baseline))
    after = Counter(re.findall(r"[\w]+(?:[.,][0-9]+)*", candidate))
    missing, added = before - after, after - before
    return {
        "state": "no_baseline" if not baseline.strip() else
                 "same_tokens" if not missing and not added else "different",
        "baseline_sha256": hashlib.sha256(baseline.encode()).hexdigest(),
        "baseline_chars": len(baseline), "candidate_chars": len(candidate),
        "missing_token_count": sum(missing.values()), "added_token_count": sum(added.values()),
        "missing_examples": list(missing)[:50], "added_examples": list(added)[:50],
        "verified": False,
    }
