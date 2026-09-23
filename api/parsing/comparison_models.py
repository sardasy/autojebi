"""Public v2 comparison result contract; offsets index the named comparison texts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Change(Model):
    kind: Literal["content", "whitespace", "unclassified"]
    before_start: int = Field(ge=0)
    before_end: int = Field(ge=0)
    after_start: int = Field(ge=0)
    after_end: int = Field(ge=0)
    before: str
    after: str
    before_context: str
    after_context: str


class Difference(Model):
    before_text: str
    after_text: str
    changes: list[Change] = Field(max_length=500)
    completion: Literal["complete", "truncated"]


class CellDifference(Difference):
    row: int = Field(ge=0)
    col: int = Field(ge=0)


class TableDifference(Model):
    reference_table_id: str | None
    locator: str
    parent_cell: str | None = None
    status: Literal["matched", "unmatched", "structure_changed"]
    cells: list[CellDifference]
    row_diff: Difference | None = None


class Summary(Model):
    content: int
    whitespace: int
    unclassified: int
    control_groups: int
    changed_cells: int
    unmatched_tables: int
    structure_changes: int
    cells_not_compared: bool


class Control(Model):
    locator: str
    start: int
    end: int
    text: str


class ComparisonResult(Difference):
    comparison_version: Literal[2]
    offset_unit: Literal["unicode_codepoint"]
    offset_basis: Literal["comparison_text"]
    basis: Literal["stored", "current_extraction", "legacy_extraction"]
    controls: list[Control]
    tables: list[TableDifference]
    summary: Summary
    has_baseline: bool
    verified: Literal[False]
    truncation_reason: str | None = None
