"""Restricted Markdown to deterministic Hancom field layout; no executable markup."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from markdown_it import MarkdownIt
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Run(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,99}$")
    bold: bool = False
    italic: bool = False


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["paragraph", "heading", "table", "page_break"]
    level: int = Field(default=1, ge=1, le=6)
    runs: list[Run] = Field(default_factory=list, max_length=500)
    rows: list[list[list[Run]]] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def shape(self):
        if self.kind == "table":
            if self.runs or not self.rows or not 1 <= len(self.rows[0]) <= 12:
                raise ValueError("invalid_table")
            if any(len(row) != len(self.rows[0]) or any(not cell for cell in row) for row in self.rows):
                raise ValueError("ragged_table")
        elif self.rows or (self.kind == "page_break" and self.runs):
            raise ValueError("invalid_block")
        return self


class Layout(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1] = 1
    blocks: list[Block] = Field(min_length=1, max_length=2000)

    def fields(self) -> list[str]:
        return [run.field for block in self.blocks for run in (
            [run for row in block.rows for cell in row for run in cell]
            if block.kind == "table" else block.runs
        )]

    @model_validator(mode="after")
    def coverage(self):
        fields = self.fields()
        if not fields or len(fields) > 2000 or len(fields) != len(set(fields)):
            raise ValueError("invalid_layout_fields")
        return self

    def checksum(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()


def compile_markdown(text: str) -> tuple[Layout, dict[str, str], list[dict]]:
    if not text.strip() or len(text) > 200000:
        raise ValueError("invalid_proposal_body")
    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    tokens = parser.parse(text)
    blocks: list[Block] = []
    values: dict[str, str] = {}
    manifest: list[dict] = []
    kind, level = "paragraph", 1
    rows: list[list[list[Run]]] | None = None
    cell: list[Run] | None = None
    lists: list[int | None] = []
    list_prefix = ""

    def leaf(value: str, *, bold=False, italic=False) -> Run:
        field = f"body_{len(values):04d}"
        values[field] = value
        manifest.append({"field": field, "logical_path": "proposal.body", "ordinal": len(values) - 1,
                         "text_sha256": hashlib.sha256(value.encode()).hexdigest()})
        return Run(field=field, bold=bold, italic=italic)

    for token in tokens:
        typ = token.type
        if typ == "html_block":
            if token.content.strip() != "<!-- page -->":
                raise ValueError("unsupported_html")
            blocks.append(Block(kind="page_break"))
        elif typ in {"fence", "code_block", "blockquote_open", "hr"}:
            raise ValueError("unsupported_markdown_" + typ)
        elif typ in {"bullet_list_open", "ordered_list_open"}:
            lists.append(int(token.attrGet("start") or 1) if typ == "ordered_list_open" else None)
        elif typ in {"bullet_list_close", "ordered_list_close"}:
            lists.pop()
        elif typ == "list_item_open":
            number = lists[-1]
            list_prefix = "  " * (len(lists) - 1) + (f"{number}. " if number is not None else "• ")
            if number is not None:
                lists[-1] = number + 1
        elif typ == "heading_open":
            kind, level = "heading", int(token.tag[1:])
        elif typ == "heading_close":
            kind = "paragraph"
        elif typ == "table_open":
            rows = []
        elif typ == "tr_open":
            assert rows is not None
            rows.append([])
        elif typ in {"th_open", "td_open"}:
            cell = []
        elif typ in {"th_close", "td_close"}:
            assert rows is not None and cell is not None
            rows[-1].append(cell or [leaf("")])
            cell = None
        elif typ == "table_close":
            blocks.append(Block(kind="table", rows=rows or []))
            rows = None
        elif typ == "inline":
            runs: list[Run] = []
            bold, italic = False, False
            link: tuple[str, list[str]] | None = None
            leading_space = ""

            def append_run(value: str, *, bold=False, italic=False, target: list[Run] = runs) -> None:
                nonlocal leading_space
                if not value.strip():
                    if target:
                        field = target[-1].field
                        values[field] += value
                        manifest[-1]["text_sha256"] = hashlib.sha256(values[field].encode()).hexdigest()
                    else:
                        leading_space += value
                else:
                    target.append(leaf(leading_space + value, bold=bold, italic=italic))
                    leading_space = ""

            if list_prefix:
                append_run(list_prefix)
                list_prefix = ""
            for child in token.children or []:
                if child.type in {"text", "code_inline"}:
                    if link is not None:
                        link[1].append(child.content)
                    if child.content:
                        append_run(child.content, bold=bold, italic=italic)
                elif child.type in {"softbreak", "hardbreak"}:
                    if link is not None:
                        link[1].append("\n")
                    append_run("\n")
                elif child.type == "strong_open":
                    bold = True
                elif child.type == "strong_close":
                    bold = False
                elif child.type == "em_open":
                    italic = True
                elif child.type == "em_close":
                    italic = False
                elif child.type == "link_open":
                    href = child.attrGet("href") or ""
                    if not re.match(r"^https?://", href):
                        raise ValueError("unsupported_link")
                    link = (href, [])
                elif child.type == "link_close":
                    if link is not None:
                        href, caption = link
                        if "".join(caption) != href:
                            append_run(f" ({href})")
                        link = None
                else:
                    raise ValueError("unsupported_inline_" + child.type)
            if leading_space:
                raise ValueError("unsupported_blank_inline")
            if cell is not None:
                cell.extend(runs)
            elif runs:
                blocks.append(Block(kind=kind, level=level, runs=runs))
    layout = Layout(blocks=blocks)
    if layout.fields() != list(values):
        raise ValueError("layout_content_order_mismatch")
    return layout, values, manifest
