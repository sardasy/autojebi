"""Validate the local Worker's saved-file evidence, independently of its success flag."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.hwp_worker.field_text import normalize
from api.workspace.hwp_validation import HwpValidationError


class Occurrence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    field: str = Field(min_length=1, max_length=200)
    occurrence: int = Field(ge=0)


class SavedValue(Occurrence):
    value: str = Field(max_length=100_000)


class Verification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    contract_version: Literal[1]
    template_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    template_fields: list[Occurrence] = Field(max_length=10_000)
    saved_fields: list[Occurrence] = Field(max_length=10_000)
    readback: list[SavedValue] = Field(max_length=10_000)
    lifecycle: list[str]


def verify_readback(
    raw: dict, values: dict[str, str], template_sha256: str, output_sha256: str,
) -> dict | None:
    if "verification" not in raw:
        return None
    try:
        proof = Verification.model_validate(raw["verification"])
    except ValidationError:
        raise HwpValidationError("invalid saved-field evidence") from None
    if type(raw["verification"].get("contract_version")) is not int:
        raise HwpValidationError("invalid verification version")
    if proof.template_sha256 != template_sha256 or proof.output_sha256 != output_sha256:
        raise HwpValidationError("saved-field evidence is for a different file")
    if proof.lifecycle != ["opened", "written", "saved", "closed", "reopened", "readback", "closed", "quit"]:
        raise HwpValidationError("incomplete Hancom execution lifecycle")

    def identities(items: list[Occurrence]) -> set[tuple[str, int]]:
        result = {(item.field, item.occurrence) for item in items}
        if len(result) != len(items):
            raise HwpValidationError("duplicate field occurrence")
        for name in {item.field for item in items}:
            if any(char in name for char in ("\x00", "\x02", "{{", "}}")) or not name.strip():
                raise HwpValidationError("ambiguous field name")
            numbers = sorted(index for field, index in result if field == name)
            if numbers != list(range(len(numbers))):
                raise HwpValidationError("incomplete field occurrences")
        return result

    original = identities(proof.template_fields)
    saved = identities(proof.saved_fields)
    readback = identities(proof.readback)
    if original != saved or saved != readback:
        raise HwpValidationError("template/save/readback field coverage differs")
    names = {name for name, _ in saved}
    if set(raw.get("fields") or []) != names:
        raise HwpValidationError("field enumeration disagrees with report")
    if set(raw.get("missing") or []) != set(values) - names:
        raise HwpValidationError("missing fields disagree with enumeration")
    if set(raw.get("replaced") or []) != set(values) & names:
        raise HwpValidationError("replaced fields disagree with enumeration")
    residual = set()
    for item in proof.readback:
        text = normalize(item.value)
        if item.field in values and text != normalize(values[item.field]):
            raise HwpValidationError("saved field does not match requested value")
        if not text.strip() or re.search(r"\{\{[^{}]+\}\}|\[검증필요\]", text):
            residual.add(item.field)
    if set(raw.get("remaining_placeholders") or []) != residual:
        raise HwpValidationError("remaining fields disagree with saved values")
    return {
        "contract_version": "hwp-saved-fields-v1",
        "field_enumeration": "passed", "field_readback": "passed",
        "com_execution": "reported_complete", "verified": True,
        "saved_occurrence_count": len(saved), "layout_review": "required",
    }
