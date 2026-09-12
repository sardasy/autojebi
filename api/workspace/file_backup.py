"""Streaming, verified file backups. No settings, database access, or automatic recovery."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Literal

from pydantic import BaseModel, ConfigDict, Field

CHUNK_SIZE = 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_FILES = 100_000
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
INCOMPLETE_MARKER = ".restore-incomplete.json"
RESTORE_REPORT = "restore-report.json"


class BackupError(RuntimeError):
    """A rejected or incomplete backup/restore; existing artifacts are never removed."""


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1]
    roots: dict[str, str]
    entries: list[_Entry]


@dataclass(frozen=True)
class _Source:
    path: Path
    signature: tuple[int, ...]


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _no_links(path: Path) -> None:
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BackupError("linked_path")


def _absolute(path: Path) -> Path:
    path = Path(path)
    lexical = path if path.is_absolute() else Path.cwd() / path
    _no_links(lexical)
    return lexical.resolve()


def _directory(path: Path) -> Path:
    path = _absolute(path)
    if not path.is_dir():
        raise BackupError("directory_required")
    return path


def _new_target(path: Path) -> Path:
    path = _absolute(path)
    if os.path.lexists(path):
        raise BackupError("destination_exists")
    _directory(path.parent)
    return path


def _fold(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _parts(value: str) -> list[str]:
    if not value or "\\" in value or value.startswith("/"):
        raise BackupError("unsafe_archive_path")
    parts = value.split("/")
    for part in parts:
        if (
            not part
            or part in {".", ".."}
            or part.endswith((".", " "))
            or any(ord(char) < 32 or ord(char) == 127 or char in ':<>"|?*' for char in part)
        ):
            raise BackupError("unsafe_archive_path")
        stem = unicodedata.normalize("NFKC", part.split(".", 1)[0]).upper()
        if stem in {"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$"} or re.fullmatch(
            r"(?:COM|LPT)[1-9]",
            stem,
        ):
            raise BackupError("device_archive_path")
    return parts


def _labels(roots: dict[str, str | Path]) -> None:
    if not roots:
        raise BackupError("sources_required")
    seen = set()
    for label in roots:
        if len(_parts(label)) != 1 or _fold(label) in seen:
            raise BackupError("unsafe_or_aliased_label")
        seen.add(_fold(label))


def _validate_names(names: list[str], roots: dict[str, str | Path]) -> None:
    prefixes: dict[str, str] = {}
    files: set[str] = set()
    directories: set[str] = set()
    for name in names:
        parts = _parts(name)
        if len(parts) < 3 or parts[0] != "files" or parts[1] not in roots:
            raise BackupError("unexpected_archive_path")
        key = _fold(name)
        if key in files or key in directories:
            raise BackupError("duplicate_or_conflicting_path")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            folded = _fold(prefix)
            if folded in prefixes and prefixes[folded] != prefix:
                raise BackupError("casefold_path_alias")
            prefixes[folded] = prefix
            if index < len(parts):
                if folded in files:
                    raise BackupError("file_directory_conflict")
                directories.add(folded)
        files.add(key)


def _inventory(roots: dict[str, Path]) -> dict[str, _Source]:
    inventory: dict[str, _Source] = {}
    total = 0
    for label, root in sorted(roots.items()):
        _directory(root)
        pending = [root]
        while pending:
            directory = pending.pop()
            _no_links(directory)
            with os.scandir(directory) as scan:
                children = sorted(scan, key=lambda item: item.name)
            for child in children:
                path = Path(child.path)
                _no_links(path)
                info = path.lstat()
                relative = path.relative_to(root).as_posix()
                _parts(relative)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    name = f"files/{label}/{relative}"
                    total += info.st_size
                    if len(inventory) >= MAX_FILES or total > MAX_TOTAL_BYTES:
                        raise BackupError("backup_limits_exceeded")
                    inventory[name] = _Source(path, _signature(info))
                else:
                    raise BackupError("nonregular_source")
    inventory = dict(sorted(inventory.items()))
    _validate_names(list(inventory), roots)
    return inventory


def _source_hash(source: _Source, output: BinaryIO | None = None) -> str:
    _no_links(source.path)
    if _signature(source.path.stat()) != source.signature:
        raise BackupError("source_changed")
    digest = hashlib.sha256()
    size = 0
    with source.path.open("rb") as stream:
        if _signature(os.fstat(stream.fileno())) != source.signature:
            raise BackupError("source_changed")
        while chunk := stream.read(CHUNK_SIZE):
            size += len(chunk)
            if size > source.signature[3]:
                raise BackupError("source_changed")
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
        if _signature(os.fstat(stream.fileno())) != source.signature:
            raise BackupError("source_changed")
    _no_links(source.path)
    if size != source.signature[3] or _signature(source.path.stat()) != source.signature:
        raise BackupError("source_changed")
    return digest.hexdigest()


def _archive_hash(stream: BinaryIO) -> str:
    stream.seek(0)
    digest = hashlib.sha256()
    while chunk := stream.read(CHUNK_SIZE):
        digest.update(chunk)
    return digest.hexdigest()


def _expected(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", value):
        raise BackupError("expected_archive_sha256_required")
    return value.lower()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("duplicate_manifest_key")
        result[key] = value
    return result


def _manifest(data: bytes) -> _Manifest:
    if len(data) > MAX_MANIFEST_BYTES:
        raise BackupError("manifest_too_large")
    try:
        manifest = _Manifest.model_validate(json.loads(data, object_pairs_hook=_unique_object))
    except ValueError:
        raise BackupError("invalid_manifest") from None
    _labels(manifest.roots)
    if any(
        not (PurePosixPath(root).is_absolute() or PureWindowsPath(root).is_absolute())
        for root in manifest.roots.values()
    ):
        raise BackupError("invalid_manifest_root")
    if (
        len(manifest.entries) > MAX_FILES
        or sum(entry.size for entry in manifest.entries) > MAX_TOTAL_BYTES
    ):
        raise BackupError("backup_limits_exceeded")
    _validate_names([entry.path for entry in manifest.entries], manifest.roots)
    return manifest


def _regular_member(info: zipfile.ZipInfo) -> None:
    mode = info.external_attr >> 16
    if (
        info.orig_filename != info.filename
        or info.is_dir()
        or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
        or info.external_attr & (0x10 | 0x400)
        or info.flag_bits & 1
    ):
        raise BackupError("nonregular_archive_member")


def _entry_hash(zipped: zipfile.ZipFile, entry: _Entry, output: BinaryIO | None = None) -> None:
    digest = hashlib.sha256()
    size = 0
    with zipped.open(entry.path) as stream:
        while chunk := stream.read(CHUNK_SIZE):
            size += len(chunk)
            if size > entry.size:
                raise BackupError("entry_size_mismatch")
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
    if size != entry.size or not hmac.compare_digest(digest.hexdigest(), entry.sha256):
        raise BackupError("entry_hash_mismatch")


def _verify(stream: BinaryIO, expected_sha256: str) -> _Manifest:
    before = _signature(os.fstat(stream.fileno()))
    if not hmac.compare_digest(_archive_hash(stream), expected_sha256):
        raise BackupError("archive_hash_mismatch")
    stream.seek(0)
    try:
        with zipfile.ZipFile(stream) as zipped:
            members = zipped.infolist()
            names = [info.filename for info in members]
            if len(members) > MAX_FILES + 1 or len(names) != len(set(names)):
                raise BackupError("duplicate_members_or_file_limit")
            if names.count("manifest.json") != 1:
                raise BackupError("manifest_missing")
            for info in members:
                _regular_member(info)
            metadata = zipped.getinfo("manifest.json")
            if metadata.file_size > MAX_MANIFEST_BYTES:
                raise BackupError("manifest_too_large")
            with zipped.open(metadata) as stream_manifest:
                manifest = _manifest(stream_manifest.read(MAX_MANIFEST_BYTES + 1))
            if set(names) != {"manifest.json", *(entry.path for entry in manifest.entries)}:
                raise BackupError("manifest_members_mismatch")
            for entry in manifest.entries:
                if zipped.getinfo(entry.path).file_size != entry.size:
                    raise BackupError("entry_size_mismatch")
                _entry_hash(zipped, entry)
    except (zipfile.BadZipFile, NotImplementedError, EOFError):
        raise BackupError("corrupt_archive") from None
    if _signature(os.fstat(stream.fileno())) != before:
        raise BackupError("archive_changed")
    return manifest


def _archive_path(archive: Path) -> Path:
    path = _absolute(archive)
    if not stat.S_ISREG(path.stat().st_mode):
        raise BackupError("regular_archive_required")
    return path


def create_backup(sources: dict[str, Path], archive: Path) -> dict:
    _labels(sources)
    roots = {label: _directory(path) for label, path in sources.items()}
    resolved_roots = list(roots.values())
    for index, root in enumerate(resolved_roots):
        if any(
            root.is_relative_to(other) or other.is_relative_to(root)
            for other in resolved_roots[:index]
        ):
            raise BackupError("overlapping_source_roots")
    archive = _new_target(archive)
    if any(archive.is_relative_to(root) for root in roots.values()):
        raise BackupError("archive_inside_source")
    inventory = _inventory(roots)
    entries = []
    with archive.open("x+b") as target:
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for name, source in inventory.items():
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with zipped.open(info, "w", force_zip64=True) as output:
                    checksum = _source_hash(source, output)
                entries.append({"path": name, "size": source.signature[3], "sha256": checksum})
            # The final manifest is absent unless inventory and a full second read agree.
            if _inventory(roots) != inventory:
                raise BackupError("source_changed")
            for entry in entries:
                if _source_hash(inventory[entry["path"]]) != entry["sha256"]:
                    raise BackupError("source_changed")
            if _inventory(roots) != inventory:
                raise BackupError("source_changed")
            data = json.dumps(
                {
                    "version": 1,
                    "roots": {label: str(root) for label, root in roots.items()},
                    "entries": entries,
                },
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            _manifest(data)
            zipped.writestr("manifest.json", data)
        target.flush()
        os.fsync(target.fileno())
        checksum = _archive_hash(target)
        manifest = _verify(target, checksum)
        if _inventory(roots) != inventory:
            raise BackupError("source_changed")
    return {
        "archive_sha256": checksum,
        "file_count": len(manifest.entries),
        "total_bytes": sum(entry.size for entry in manifest.entries),
    }


def verify_backup(archive: Path, expected_sha256: str) -> dict:
    expected = _expected(expected_sha256)
    with _archive_path(archive).open("rb") as stream:
        return _verify(stream, expected).model_dump()


def _write_json_new(path: Path, value: dict) -> None:
    _no_links(path)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def _restored_inventory(destination: Path, allow_incomplete: bool) -> dict[str, _Source]:
    destination = _directory(destination)
    for item in destination.iterdir():
        _no_links(item)
        if item.name == "files" and item.is_dir():
            continue
        if item.name == INCOMPLETE_MARKER and not allow_incomplete:
            raise BackupError("incomplete_restore")
        if item.name not in {RESTORE_REPORT, INCOMPLETE_MARKER} or not item.is_file():
            raise BackupError("unexpected_restore_entry")
    payload = destination / "files"
    if not payload.exists():
        return {}
    inventory = _inventory({"payload": payload})
    return {
        source.path.relative_to(destination).as_posix(): source for source in inventory.values()
    }


def _verify_restored(
    manifest: _Manifest, destination: Path, allow_incomplete: bool = False
) -> dict:
    inventory = _restored_inventory(destination, allow_incomplete)
    if set(inventory) != {entry.path for entry in manifest.entries}:
        raise BackupError("restored_members_mismatch")
    for entry in manifest.entries:
        source = inventory[entry.path]
        if source.signature[3] != entry.size or not hmac.compare_digest(
            _source_hash(source), entry.sha256
        ):
            raise BackupError("restored_file_mismatch")
    if _restored_inventory(destination, allow_incomplete) != inventory:
        raise BackupError("restored_files_changed")
    return {
        "file_count": len(manifest.entries),
        "total_bytes": sum(entry.size for entry in manifest.entries),
    }


def verify_restored(manifest: dict, destination: Path) -> dict:
    """Re-read a completed restore, treating report contents as metadata, never proof."""
    validated = _manifest(json.dumps(manifest, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    return _verify_restored(validated, _directory(destination))


def restore_backup(archive: Path, destination: Path, expected_sha256: str) -> dict:
    expected = _expected(expected_sha256)
    destination = _new_target(destination)
    with _archive_path(archive).open("rb") as stream:
        manifest = _verify(stream, expected)
        destination.mkdir(mode=0o700, exist_ok=False)
        incomplete = destination / INCOMPLETE_MARKER
        _write_json_new(incomplete, {"state": "incomplete", "archive_sha256": expected})
        stream.seek(0)
        with zipfile.ZipFile(stream) as zipped:
            for entry in manifest.entries:
                output = destination.joinpath(*entry.path.split("/"))
                _no_links(output)
                output.parent.mkdir(parents=True, exist_ok=True)
                _no_links(output)
                with output.open("xb") as target:
                    _entry_hash(zipped, entry, target)
                    target.flush()
                    os.fsync(target.fileno())
        if not hmac.compare_digest(_archive_hash(stream), expected):
            raise BackupError("archive_changed")
        summary = {
            "archive_sha256": expected,
            **_verify_restored(manifest, destination, allow_incomplete=True),
        }
        _write_json_new(destination / RESTORE_REPORT, summary)
        incomplete.unlink()
    return summary
