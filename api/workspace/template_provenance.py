"""Content-bound template origin; generated skeletons never qualify for submission approval."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from api.parsing.hwp_validation import read_hwp_output, validate_hwp_content
from api.workspace.errors import fail

DEFAULT_KEYS = frozenset({"bid_form", "proposal"})
VALIDATION_WARNING = "검증 전용 골격입니다. 항목명·공식 문구가 없어 생성 테스트만 가능하며 제출용 출력 승인과 제출 준비 완료는 할 수 없습니다."
UNCLASSIFIED_WARNING = "기본 템플릿의 출처가 확인되지 않았습니다. 기존 파일을 검증 골격이나 공식 양식으로 임의 분류하지 않으며 제출용 출력 승인을 차단합니다."
INVALID_WARNING = "템플릿 출처 기록 또는 파일이 변경되었습니다. 원본과 기록을 대조한 후 다시 생성하세요."


class SkeletonMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    purpose: Literal["validation_only", "source_form"] = "validation_only"
    tool: Literal["tools.prepare_default_hwp_templates"] = "tools.prepare_default_hwp_templates"
    template_key: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str = Field(min_length=20, max_length=40)
    operation_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    source_reference: str | None = Field(default=None, max_length=2000)
    reviewer_id: str | None = Field(default=None, max_length=100)
    review_note: str | None = Field(default=None, max_length=2000)
    human_reviewed: bool = False

    @model_validator(mode="after")
    def require_source_review(self):
        if self.purpose == "source_form" and (not self.human_reviewed or not all(
            value and value.strip() for value in (self.source_reference, self.reviewer_id, self.review_note)
        )):
            raise ValueError("source form requires explicit human origin review")
        if datetime.fromisoformat(self.created_at).tzinfo is None:
            raise ValueError("creation timestamp requires timezone")
        return self


class TemplateProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["validation_only", "reviewed_source", "unclassified", "untracked", "invalid", "unavailable"]
    template_key: str | None
    template_path: str | None
    template_sha256: str | None
    metadata_sha256: str | None = None
    content_record_sha256: str | None = None
    generation_allowed: bool
    approval_allowed: bool
    warning: str | None = None


def metadata_path(path: Path) -> Path:
    return path.with_name(path.name + ".provenance.json")


def content_record_path(checksum: str) -> Path:
    if not isinstance(checksum, str) or len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
        raise ValueError("invalid content hash")
    root = Path(os.getenv("HWP_TEMPLATE_ROOT", "data")).resolve()
    folder = root / ".template-provenance"
    if folder.is_symlink() or not folder.resolve().is_relative_to(root):
        raise ValueError("linked provenance registry")
    return folder / (checksum + ".json")


def read_metadata(path: Path) -> tuple[SkeletonMetadata, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_384:
        raise ValueError("invalid provenance record")
    raw = path.read_bytes()
    return SkeletonMetadata.model_validate_json(raw), hashlib.sha256(raw).hexdigest()


def serialized(metadata: SkeletonMetadata) -> bytes:
    return (json.dumps(metadata.model_dump(exclude_none=True), ensure_ascii=False,
                       sort_keys=True, indent=2) + "\n").encode("utf-8")


def write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def record_content(metadata: SkeletonMetadata) -> None:
    """Content origin is immutable, including after file/key renaming."""
    destination = content_record_path(metadata.sha256)
    destination.parent.mkdir(exist_ok=True)
    try:
        write_exclusive(destination, serialized(metadata))
    except FileExistsError:
        previous, _ = read_metadata(destination)
        if previous.sha256 != metadata.sha256 or previous.purpose != metadata.purpose:
            raise ValueError("content_origin_cannot_be_promoted") from None


def write_skeleton_metadata(path: Path, key: str, checksum: str, operation_id: str) -> None:
    """Write before installing the new file; any partial install remains fail-closed."""
    metadata = SkeletonMetadata(template_key=key, sha256=checksum,
        created_at=datetime.now(UTC).isoformat(), operation_id=operation_id)
    record_content(metadata)
    write_exclusive(metadata_path(path), serialized(metadata))


def record_validation_derivative(provenance: dict, checksum: str) -> None:
    """Filled/generated copies of a known skeleton retain its non-submission origin."""
    if provenance["state"] == "validation_only":
        record_content(SkeletonMetadata(template_key=provenance["template_key"], sha256=checksum,
            created_at=datetime.now(UTC).isoformat(), operation_id=uuid4().hex))


def register_source_form(template: dict, expected_sha256: str, *, source_reference: str,
                         reviewer_id: str, review_note: str, human_reviewed: bool,
                         expected_metadata_sha256: str | None = None) -> dict:
    """Administrative attestation only; artifact/layout approval remains a separate workflow."""
    current = inspect_provenance(template)
    if current["template_sha256"] != expected_sha256 or not current["template_path"]:
        raise ValueError("template_hash_confirmation_required")
    path = Path(current["template_path"])
    root = Path(os.getenv("HWP_TEMPLATE_ROOT", "data")).resolve()
    if not path.is_relative_to(root):
        raise ValueError("template_path_not_allowed")
    validate_hwp_content(read_hwp_output(path), path.suffix.lower())
    metadata = SkeletonMetadata(template_key=template["template_key"], purpose="source_form",
        sha256=expected_sha256, created_at=datetime.now(UTC).isoformat(), operation_id=uuid4().hex,
        source_reference=source_reference, reviewer_id=reviewer_id, review_note=review_note,
        human_reviewed=human_reviewed)
    sidecar = metadata_path(path)
    previous = None
    if sidecar.exists() or sidecar.is_symlink():
        _, previous_hash = read_metadata(sidecar)
        if previous_hash != expected_metadata_sha256:
            raise ValueError("metadata_hash_confirmation_required")
        previous = sidecar.read_bytes()
    elif expected_metadata_sha256 is not None:
        raise ValueError("metadata_changed")
    record_content(metadata)  # An existing skeleton content hash cannot become a source form.
    if previous is not None:
        archive = content_record_path(expected_sha256).parent / ("history-" + hashlib.sha256(previous).hexdigest() + ".json")
        if not archive.exists():
            write_exclusive(archive, previous)
    staged = sidecar.with_name(sidecar.name + "." + metadata.operation_id + ".tmp")
    write_exclusive(staged, serialized(metadata))
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("template_changed_before_registration")
    if (sidecar.read_bytes() if sidecar.exists() else None) != previous:
        raise ValueError("metadata_changed_before_registration")
    os.replace(staged, sidecar)
    return inspect_provenance(template)


def inspect_provenance(template: dict, *, path: Path | None = None,
                       checksum: str | None = None) -> dict:
    root = Path(os.getenv("HWP_TEMPLATE_ROOT", "data")).resolve()
    key = template.get("template_key")
    relative = template.get("template_path")
    candidate = path or (Path(relative) if relative else None)
    candidate = ((candidate if candidate.is_absolute() else root / candidate).resolve()
                 if candidate is not None else None)
    result = TemplateProvenance(state="unavailable", template_key=key,
        template_path=str(candidate) if candidate else None, template_sha256=checksum,
        generation_allowed=False, approval_allowed=False, warning="허용된 템플릿 원본 파일을 확인하세요.")
    if candidate is None or not candidate.is_relative_to(root) or not candidate.is_file():
        return result.model_dump()
    try:
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        result.template_sha256 = actual
        if checksum is not None and actual != checksum:
            raise ValueError("template changed")
        content_path = content_record_path(actual)
        origin = None
        if content_path.exists() or content_path.is_symlink():
            origin, result.content_record_sha256 = read_metadata(content_path)
            if origin.sha256 != actual:
                raise ValueError("content record mismatch")
        sidecar = metadata_path(candidate)
        if not sidecar.exists() and not sidecar.is_symlink():
            if origin and origin.purpose == "validation_only":
                result.state = "validation_only"
                result.generation_allowed = True
                result.warning = VALIDATION_WARNING
                return result.model_dump()
            unknown = key in DEFAULT_KEYS
            result.state = "unclassified" if unknown else "untracked"
            result.generation_allowed = True
            result.approval_allowed = not unknown
            result.warning = UNCLASSIFIED_WARNING if unknown else None
            return result.model_dump()
        metadata, result.metadata_sha256 = read_metadata(sidecar)
        if (metadata.template_key != key or metadata.sha256 != actual or origin is None
                or origin.purpose != metadata.purpose):
            raise ValueError("metadata mismatch")
        validation = metadata.purpose == "validation_only"
        result.state = "validation_only" if validation else "reviewed_source"
        result.generation_allowed = True
        result.approval_allowed = not validation
        result.warning = VALIDATION_WARNING if validation else None
    except (OSError, ValueError, ValidationError):
        result.state = "invalid"
        result.generation_allowed = False
        result.approval_allowed = False
        result.warning = INVALID_WARNING
    return result.model_dump()


def require_generation_provenance(template: dict, path: Path, checksum: str) -> dict:
    result = inspect_provenance(template, path=path, checksum=checksum)
    if not result["generation_allowed"]:
        fail("template_provenance_invalid", result["warning"] or INVALID_WARNING)
    return result


def confirm_provenance_unchanged(template: dict, path: Path, checksum: str, expected: dict) -> None:
    if inspect_provenance(template, path=path, checksum=checksum) != expected:
        fail("template_provenance_changed", INVALID_WARNING)


def review_provenance_issues(result: dict, template_key: str | None = None) -> list[str]:
    """Recheck persisted origin at every approval/package check, including legacy defaults."""
    key = template_key or result.get("template_key")
    saved = result.get("template_provenance")
    if saved is None:
        checksum = result.get("template_sha256")
        if checksum:
            try:
                path = content_record_path(checksum)
                if path.exists() or path.is_symlink():
                    record, _ = read_metadata(path)
                    if record.sha256 != checksum:
                        return [INVALID_WARNING]
                    if record.purpose == "validation_only":
                        return [VALIDATION_WARNING]
            except (OSError, ValueError, ValidationError):
                return [INVALID_WARNING]
        return [UNCLASSIFIED_WARNING] if key in DEFAULT_KEYS else []
    try:
        proof = TemplateProvenance.model_validate(saved)
    except ValidationError:
        return [INVALID_WARNING]
    if key and proof.template_key != key:
        return [INVALID_WARNING]
    if proof.template_sha256 != result.get("template_sha256"):
        return [INVALID_WARNING]
    if not proof.approval_allowed:
        return [proof.warning or INVALID_WARNING]
    current = inspect_provenance({"template_key": proof.template_key, "template_path": proof.template_path},
                                checksum=proof.template_sha256)
    if current != proof.model_dump() or not current["approval_allowed"]:
        return [INVALID_WARNING]
    return []
