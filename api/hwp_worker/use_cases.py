"""Document operations inside one owned session, without HTTP or COM activation.

The session protocol is the integration boundary for a future pyhwpx adapter.
Adapters must use the Worker's owned COM object; a library constructor must not
attach to the user's session, register modules, or manage COM/thread lifetime.
The generator keeps inspect -> mapping -> render -> validate -> previews inside
one queue/mutex/recovery operation. PDF conversion is not implemented here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from api.hwp_worker.errors import ComDriverError
from api.hwp_worker.field_text import mismatch_summary, normalize

RESIDUAL = re.compile(r"\{\{[^{}]+\}\}|\[검증필요\]")


class DocumentSession(Protocol):
    """Operations on an already owned session; never an alternative COM host."""

    lifecycle: list[str]

    def open(self, path: Path, *, reopen: bool = False) -> None: ...
    def close(self) -> None: ...
    def enumerate(self) -> list[dict[str, Any]]: ...
    def read(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
    def write(self, name: str, value: str) -> None: ...
    def save(self, output: Path, output_format: str) -> None: ...
    def text(self) -> str: ...
    def page_images(self, output: Path) -> list[dict[str, Any]]: ...
    def fingerprint(self, path: Path, stage: str) -> str: ...
    def require_new_output(self, output: Path) -> None: ...


@dataclass(frozen=True)
class Inspection:
    sha256: str
    fields: list[dict[str, Any]]


@dataclass(frozen=True)
class FieldMapping:
    replaced: list[str]
    missing: list[str]


@dataclass(frozen=True)
class Validation:
    sha256: str
    fields: list[dict[str, Any]]
    readback: list[dict[str, Any]]


def field_names(fields: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(item["field"] for item in fields))


def remaining_fields(readback: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(
        item["field"] for item in readback
        if not item["value"].strip() or RESIDUAL.search(item["value"])
    ))


def inspect_document(
    session: DocumentSession, path: Path, *, hash_stage: str = "source_hash",
) -> Inspection:
    """Open and enumerate the input; the owning operation closes the session."""
    checksum = session.fingerprint(path, hash_stage)
    session.open(path)
    return Inspection(checksum, session.enumerate())


def map_fields(inspection: Inspection, values: dict[str, str]) -> FieldMapping:
    names = set(field_names(inspection.fields))
    return FieldMapping(
        [name for name in values if name in names],
        [name for name in values if name not in names],
    )


def render_document(
    session: DocumentSession, output: Path, output_format: str,
    values: dict[str, str], mapping: FieldMapping,
) -> None:
    """Write mapped fields and close the saved document before validation."""
    for name in mapping.replaced:
        session.write(name, values[name])
    session.lifecycle.append("written")
    session.require_new_output(output)
    session.save(output, output_format)
    session.lifecycle.append("saved")
    session.close()


def validate_document(
    session: DocumentSession, output: Path, inspection: Inspection, values: dict[str, str],
) -> Validation:
    """Reopen and compare every field occurrence; no human approval is implied."""
    checksum = session.fingerprint(output, "output_hash")
    session.open(output, reopen=True)
    fields = session.enumerate()
    if fields != inspection.fields:
        raise ComDriverError("saved_fields_mismatch", "verify")
    readback = session.read(fields)
    for index, item in enumerate(readback):
        if item["field"] in values and normalize(item["value"]) != normalize(values[item["field"]]):
            error = ComDriverError("saved_value_mismatch", "verify")
            error.verification_detail = {
                "field_index": index,
                "occurrence": item["occurrence"],
                **mismatch_summary(values[item["field"]], item["value"]),
            }
            raise error
    return Validation(checksum, fields, readback)


def convert_document(
    session: DocumentSession, output: Path, *, target: Literal["page_images"] = "page_images",
) -> list[dict[str, Any]]:
    """Produce the supported PNG previews from the reopened document.

    PDF needs its own capability, output path policy, and real-file validation.
    An unsupported target must never fall back to another output format.
    """
    if target != "page_images":
        raise ComDriverError("unsupported_conversion_target", "convert")
    return session.page_images(output)


def generate_document(
    session: DocumentSession, template: Path, output: Path, values: dict[str, str],
    *, render_pages: bool = False,
) -> dict[str, Any]:
    """Orchestrate all use cases without releasing the owned session between stages."""
    output_format = {".hwp": "HWP", ".hwpx": "HWPX"}.get(output.suffix.lower())
    if output_format is None:
        raise ComDriverError("unsupported_output_format", "input")
    session.require_new_output(output)
    inspection = inspect_document(session, template, hash_stage="template_hash")
    mapping = map_fields(inspection, values)
    render_document(session, output, output_format, values, mapping)
    validation = validate_document(session, output, inspection, values)
    pages = convert_document(session, output) if render_pages else []
    session.close()
    if session.fingerprint(output, "output_hash") != validation.sha256:
        raise ComDriverError("saved_file_changed", "verify")
    if session.fingerprint(template, "template_hash") != inspection.sha256:
        raise ComDriverError("template_changed", "verify")
    remaining = remaining_fields(validation.readback)
    names = field_names(inspection.fields)
    warnings = []
    if mapping.missing:
        warnings.append("요청한 필드 중 템플릿에 없는 항목이 있습니다.")
    if any(name not in values for name in names) or not inspection.fields:
        warnings.append("입력 매핑이 없는 템플릿 필드 또는 빈 필드 목록을 확인하세요.")
    if remaining:
        warnings.append("비어 있거나 검증이 필요한 필드가 있습니다.")
    return {
        "output_path": str(output),
        "replaced": mapping.replaced,
        "missing": mapping.missing,
        "remaining_placeholders": remaining,
        "fields": field_names(validation.fields),
        "warnings": warnings,
        "pages": pages,
        "verification": {
            "contract_version": 1,
            "template_sha256": inspection.sha256,
            "output_sha256": validation.sha256,
            "template_fields": inspection.fields,
            "saved_fields": validation.fields,
            "readback": validation.readback,
            # The owner appends quit before returning this result to HTTP.
            "lifecycle": session.lifecycle,
        },
    }
