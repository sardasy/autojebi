"""Isolated file backup tests; no settings, database, or production files."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
import warnings
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.workspace import file_backup as backup
from api.workspace.file_backup import (
    BackupError,
    create_backup,
    restore_backup,
    verify_backup,
    verify_restored,
)


@pytest.fixture
def roots(tmp_path):
    sources = {label: tmp_path / label for label in ("uploads", "database")}
    for root in sources.values():
        root.mkdir()
    return sources


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_for(root: Path, entries: list[tuple[str, bytes]]) -> dict:
    return {
        "version": 1,
        "roots": {"uploads": str(root)},
        "entries": [
            {"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in entries
        ],
    }


def make_zip(path: Path, root: Path, entries: list[tuple[str, bytes]], manifest=None) -> str:
    if manifest is None:
        manifest = manifest_for(root, entries)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zipped:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Duplicate name:.*", category=UserWarning)
            for name, data in entries:
                zipped.writestr(name, data)
        zipped.writestr("manifest.json", json.dumps(manifest))
    return sha(path)


def test_binary_korean_hidden_empty_file_and_database_round_trip(roots, tmp_path):
    payloads = {
        "uploads/binary.bin": bytes(range(256)) * (backup.CHUNK_SIZE // 128 + 1),
        "uploads/\uacf5\uace0-\uc11c\ub958.txt": "\ud55c\uae00 \ubcf8\ubb38".encode(),
        "uploads/.hidden": b"hidden data",
        "uploads/empty.bin": b"",
        "database/snapshot.bin": b"\x00\xffdatabase snapshot\x00",
    }
    for name, data in payloads.items():
        (tmp_path / name).write_bytes(data)
    (roots["uploads"] / "empty-directory").mkdir()
    archive = tmp_path / "backup.zip"
    summary = create_backup(roots, archive)
    assert summary == {
        "archive_sha256": sha(archive),
        "file_count": len(payloads),
        "total_bytes": sum(map(len, payloads.values())),
    }
    manifest = verify_backup(archive, summary["archive_sha256"])
    assert manifest["version"] == 1
    assert manifest["roots"] == {label: str(root.resolve()) for label, root in roots.items()}
    assert [entry["path"] for entry in manifest["entries"]] == sorted(
        "files/" + key for key in payloads
    )
    destination = tmp_path / "restored"
    assert restore_backup(archive, destination, summary["archive_sha256"]) == summary
    for name, data in payloads.items():
        assert (destination / "files" / name).read_bytes() == data
    assert json.loads((destination / backup.RESTORE_REPORT).read_bytes()) == summary
    assert not (destination / backup.INCOMPLETE_MARKER).exists()
    assert not (destination / "files/uploads/empty-directory").exists()
    assert verify_restored(manifest, destination) == {
        "file_count": summary["file_count"],
        "total_bytes": summary["total_bytes"],
    }


def test_empty_roots_are_valid_without_directory_entries(roots, tmp_path):
    archive = tmp_path / "empty.zip"
    summary = create_backup(roots, archive)
    assert summary["file_count"] == summary["total_bytes"] == 0
    assert verify_backup(archive, summary["archive_sha256"])["entries"] == []
    destination = tmp_path / "restored"
    assert restore_backup(archive, destination, summary["archive_sha256"]) == summary
    assert list(destination.iterdir()) == [destination / backup.RESTORE_REPORT]


@pytest.mark.parametrize("invalid", [None, "", "wrong", "g" * 64, "0" * 64])
def test_expected_archive_hash_is_mandatory_and_checked_before_restore(roots, tmp_path, invalid):
    archive = tmp_path / "backup.zip"
    create_backup(roots, archive)
    with pytest.raises(BackupError):
        verify_backup(archive, invalid)
    destination = tmp_path / "restored"
    with pytest.raises(BackupError):
        restore_backup(archive, destination, invalid)
    assert not destination.exists()


def test_existing_archive_is_never_overwritten(roots, tmp_path):
    archive = tmp_path / "keep.zip"
    archive.write_bytes(b"user content")
    with pytest.raises(BackupError, match="destination_exists"):
        create_backup(roots, archive)
    assert archive.read_bytes() == b"user content"


def test_archive_inside_source_is_refused(roots):
    archive = roots["uploads"] / ".hidden-backup.zip"
    with pytest.raises(BackupError, match="archive_inside_source"):
        create_backup(roots, archive)
    assert not archive.exists()


@pytest.mark.parametrize("overlap", ["identical", "normalized", "parent-first", "child-first"])
def test_overlapping_roots_rejected_before_inventory_or_archive(
    roots, tmp_path, monkeypatch, overlap
):
    parent = roots["uploads"]
    child = parent / "nested"
    child.mkdir()
    if overlap == "identical":
        paths = (parent, parent)
    elif overlap == "normalized":
        paths = (parent, child / "..")
    elif overlap == "parent-first":
        paths = (parent, child)
    else:
        paths = (child, parent)
    archive = tmp_path / "overlap.zip"
    monkeypatch.setattr(backup, "_inventory", lambda _: pytest.fail("overlap reached inventory"))
    with pytest.raises(BackupError, match="overlapping_source_roots"):
        create_backup(dict(zip(("first", "second"), paths, strict=True)), archive)
    assert not archive.exists()


def test_sibling_roots_with_shared_name_prefix_are_allowed(roots, tmp_path):
    sibling = tmp_path / "uploads-extra"
    sibling.mkdir()
    (roots["uploads"] / "one").write_bytes(b"one")
    (sibling / "two").write_bytes(b"two")
    archive = tmp_path / "siblings.zip"
    summary = create_backup({"uploads": roots["uploads"], "extra": sibling}, archive)
    assert summary["file_count"] == 2
    assert len(verify_backup(archive, summary["archive_sha256"])["entries"]) == 2


def test_sources_must_be_directories(tmp_path):
    source = tmp_path / "file"
    source.write_bytes(b"file")
    with pytest.raises(BackupError, match="directory_required"):
        create_backup({"uploads": source}, tmp_path / "backup.zip")


@pytest.mark.parametrize("label", ["..", "a/b", "A:B", "NUL", "trailing."])
def test_labels_are_portable_single_components(roots, tmp_path, label):
    with pytest.raises(BackupError):
        create_backup({label: roots["uploads"]}, tmp_path / "backup.zip")


def test_casefold_source_labels_are_rejected(roots, tmp_path):
    with pytest.raises(BackupError):
        create_backup(
            {"Data": roots["uploads"], "data": roots["database"]}, tmp_path / "backup.zip"
        )


def test_restore_refuses_existing_even_empty_destination(roots, tmp_path):
    archive = tmp_path / "backup.zip"
    summary = create_backup(roots, archive)
    destination = tmp_path / "restored"
    destination.mkdir()
    with pytest.raises(BackupError, match="destination_exists"):
        restore_backup(archive, destination, summary["archive_sha256"])
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize(
    "name",
    [
        "files/uploads/../escape",
        "/files/uploads/absolute",
        "files\\uploads\\bad",
        "files/uploads/file:stream.hwp",
        "files/uploads/CON.txt",
        "files/uploads/NUL",
        "files/uploads/LPT1.hwp",
        "files/uploads/COM\u00b9.txt",
        "files/uploads/trailing.",
        "files/uploads/trailing ",
        "files/uploads/./file",
        "files/uploads//file",
        "files/uploads/bad\x01name",
        "restore-report.json",
        "files/unknown/file",
    ],
)
def test_unsafe_archive_names_rejected_before_destination_creation(roots, tmp_path, name):
    archive = tmp_path / "hostile.zip"
    checksum = make_zip(archive, roots["uploads"], [(name, b"bad")])
    destination = tmp_path / "restored"
    with pytest.raises(BackupError):
        restore_backup(archive, destination, checksum)
    assert not destination.exists()


@pytest.mark.parametrize(
    "names",
    [
        ["files/uploads/A.txt", "files/uploads/a.txt"],
        ["files/uploads/Dir/a", "files/uploads/dir/b"],
        ["files/uploads/a", "files/uploads/a/b"],
        ["files/uploads/a/b", "files/uploads/a"],
        ["files/uploads/\u00e9.txt", "files/uploads/e\u0301.txt"],
        ["files/uploads/a", "files/uploads/a"],
    ],
)
def test_alias_duplicate_and_file_directory_conflicts(roots, tmp_path, names):
    archive = tmp_path / "aliases.zip"
    checksum = make_zip(archive, roots["uploads"], [(name, b"x") for name in names])
    with pytest.raises(BackupError):
        verify_backup(archive, checksum)


@pytest.mark.parametrize("difference", ["extra", "missing", "duplicate-manifest", "no-manifest"])
def test_exact_manifest_membership(roots, tmp_path, difference):
    archive = tmp_path / "mismatch.zip"
    entries = [("files/uploads/a", b"a")]
    manifest = manifest_for(roots["uploads"], entries)
    if difference == "extra":
        checksum = make_zip(
            archive, roots["uploads"], entries + [("files/uploads/b", b"b")], manifest
        )
    elif difference == "missing":
        checksum = make_zip(archive, roots["uploads"], [], manifest)
    else:
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr(entries[0][0], entries[0][1])
            if difference == "duplicate-manifest":
                zipped.writestr("manifest.json", json.dumps(manifest))
                with pytest.warns(UserWarning, match="Duplicate name"):
                    zipped.writestr("manifest.json", json.dumps(manifest))
        checksum = sha(archive)
    with pytest.raises(BackupError):
        verify_backup(archive, checksum)


@pytest.mark.parametrize(
    "mode,dos_flags",
    [(stat.S_IFLNK, 0), (stat.S_IFCHR, 0), (stat.S_IFDIR, 0), (stat.S_IFREG, 0x400)],
)
def test_archive_link_and_special_modes_rejected(roots, tmp_path, mode, dos_flags):
    archive = tmp_path / "links.zip"
    name, data = "files/uploads/link", b"outside-target"
    with zipfile.ZipFile(archive, "w") as zipped:
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = (mode | 0o600) << 16 | dos_flags
        zipped.writestr(info, data)
        zipped.writestr("manifest.json", json.dumps(manifest_for(roots["uploads"], [(name, data)])))
    with pytest.raises(BackupError, match="nonregular_archive_member"):
        verify_backup(archive, sha(archive))


@pytest.mark.parametrize("limit", ["MAX_MANIFEST_BYTES", "MAX_FILES", "MAX_TOTAL_BYTES"])
def test_zip_bomb_limits_checked_before_entry_decompression(roots, tmp_path, monkeypatch, limit):
    archive = tmp_path / "bounds.zip"
    checksum = make_zip(
        archive, roots["uploads"], [("files/uploads/a", b"a" * 2048), ("files/uploads/b", b"b")]
    )
    monkeypatch.setattr(backup, limit, 1)
    monkeypatch.setattr(
        backup, "_entry_hash", lambda *args: pytest.fail("payload read before limits")
    )
    with pytest.raises(BackupError):
        verify_backup(archive, checksum)


@pytest.mark.parametrize("field,value", [("size", 999), ("sha256", "0" * 64), ("size", -1)])
def test_entry_size_and_sha_verified(roots, tmp_path, field, value):
    archive = tmp_path / "entry.zip"
    entries = [("files/uploads/a", b"data")]
    manifest = manifest_for(roots["uploads"], entries)
    manifest["entries"][0][field] = value
    checksum = make_zip(archive, roots["uploads"], entries, manifest)
    with pytest.raises(BackupError):
        verify_backup(archive, checksum)


def test_crc_corruption_rejected_even_with_matching_archive_sha(roots, tmp_path):
    archive = tmp_path / "crc.zip"
    make_zip(archive, roots["uploads"], [("files/uploads/a", b"CRC-PAYLOAD-123")])
    with zipfile.ZipFile(archive) as zipped:
        offset = zipped.getinfo("files/uploads/a").header_offset
    contents = bytearray(archive.read_bytes())
    name_length, extra_length = struct.unpack_from("<HH", contents, offset + 26)
    contents[offset + 30 + name_length + extra_length] ^= 1
    archive.write_bytes(contents)
    with pytest.raises(BackupError, match="corrupt_archive"):
        verify_backup(archive, sha(archive))


@pytest.mark.parametrize("kind", ["root", "parent", "file", "directory"])
def test_filesystem_links_rejected_without_following(roots, tmp_path, kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file").write_bytes(b"outside")
    link = tmp_path / "root-link" if kind in {"root", "parent"} else roots["uploads"] / "link"
    target = outside / "file" if kind == "file" else outside
    try:
        link.symlink_to(target, target_is_directory=kind != "file")
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314 or exc.errno in {1, 13, 38, 95}:
            pytest.skip("symlink creation not permitted on this test host")
        raise
    if kind in {"root", "parent"}:
        if kind == "parent":
            (outside / "nested").mkdir()
        roots = {"uploads": link if kind == "root" else link / "nested"}
    with pytest.raises(BackupError, match="linked_path"):
        create_backup(roots, tmp_path / "backup.zip")


def test_windows_junction_attribute_rejected(roots, tmp_path, monkeypatch):
    linked = roots["uploads"] / "junction"
    linked.mkdir()
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        if path == linked:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(BackupError, match="linked_path"):
        create_backup(roots, tmp_path / "backup.zip")


@pytest.mark.parametrize("change", ["add", "remove", "rewrite"])
def test_source_changes_abort_and_leave_no_complete_manifest(roots, tmp_path, monkeypatch, change):
    source = roots["uploads"] / "a"
    source.write_bytes(b"first")
    archive = tmp_path / "partial.zip"
    original = backup._source_hash
    changed = []

    def source_hash(item, output=None):
        result = original(item, output)
        if output is not None and not changed:
            changed.append(True)
            if change == "add":
                (roots["uploads"] / ".new-hidden").write_bytes(b"new")
            elif change == "remove":
                source.unlink()
            else:
                source.write_bytes(b"changed")
        return result

    monkeypatch.setattr(backup, "_source_hash", source_hash)
    with pytest.raises(BackupError, match="source_changed"):
        create_backup(roots, archive)
    assert archive.exists()
    with pytest.raises(BackupError, match="manifest_missing"):
        verify_backup(archive, sha(archive))


def test_second_source_read_detects_same_size_metadata_preserving_change(
    roots, tmp_path, monkeypatch
):
    source = roots["uploads"] / "a"
    source.write_bytes(b"first")
    original_signature, original_hash = backup._signature, backup._source_hash
    monkeypatch.setattr(backup, "_signature", lambda info: (*original_signature(info)[:4], 0, 0))
    reads = []

    def source_hash(item, output=None):
        result = original_hash(item, output)
        reads.append(output is not None)
        if output is not None:
            source.write_bytes(b"other")
        return result

    monkeypatch.setattr(backup, "_source_hash", source_hash)
    with pytest.raises(BackupError, match="source_changed"):
        create_backup(roots, tmp_path / "partial.zip")
    assert reads == [True, False]


def test_restore_failure_preserves_partial_destination_and_cannot_resume(
    roots, tmp_path, monkeypatch
):
    (roots["uploads"] / "a").write_bytes(b"data")
    archive = tmp_path / "backup.zip"
    summary = create_backup(roots, archive)
    original = backup._entry_hash

    def fail_after_partial_write(zipped, entry, output=None):
        if output is not None:
            output.write(b"partial")
            raise OSError("injected disk failure")
        return original(zipped, entry, output)

    monkeypatch.setattr(backup, "_entry_hash", fail_after_partial_write)
    destination = tmp_path / "partial-restore"
    with pytest.raises(OSError, match="injected"):
        restore_backup(archive, destination, summary["archive_sha256"])
    assert (destination / backup.INCOMPLETE_MARKER).exists()
    assert not (destination / backup.RESTORE_REPORT).exists()
    assert (destination / "files/uploads/a").read_bytes() == b"partial"
    with pytest.raises(BackupError, match="destination_exists"):
        restore_backup(archive, destination, summary["archive_sha256"])
    assert (destination / "files/uploads/a").read_bytes() == b"partial"


def test_source_stat_change_during_stream_is_detected(roots, tmp_path, monkeypatch):
    source = roots["uploads"] / "a"
    source.write_bytes(b"first")
    original = Path.open

    class ChangingReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            data = self.stream.read(size)
            if data:
                previous = source.stat().st_mtime_ns
                os.utime(source, ns=(source.stat().st_atime_ns, previous + 1_000_000_000))
            return data

    def opening(path, mode="r", *args, **kwargs):
        stream = original(path, mode, *args, **kwargs)
        return ChangingReader(stream) if path == source and mode == "rb" else stream

    monkeypatch.setattr(Path, "open", opening)
    with pytest.raises(BackupError, match="source_changed"):
        create_backup(roots, tmp_path / "partial.zip")


@pytest.mark.parametrize(
    "change", ["modify", "remove", "extra", "root-extra", "case-alias", "incomplete"]
)
def test_verify_restored_rereads_disk_and_rejects_inventory_changes(roots, tmp_path, change):
    (roots["uploads"] / "a").write_bytes(b"data")
    archive = tmp_path / "backup.zip"
    summary = create_backup(roots, archive)
    manifest = verify_backup(archive, summary["archive_sha256"])
    destination = tmp_path / "restored"
    restore_backup(archive, destination, summary["archive_sha256"])
    item = destination / "files/uploads/a"
    if change == "modify":
        item.write_bytes(b"else")
    elif change == "remove":
        item.unlink()
    elif change == "extra":
        (item.parent / ".unexpected").write_bytes(b"extra")
    elif change == "root-extra":
        (destination / "unexpected").write_bytes(b"extra")
    elif change == "case-alias":
        intermediate = item.with_name("temporary-name")
        item.rename(intermediate)
        intermediate.rename(item.with_name("A"))
    else:
        (destination / backup.INCOMPLETE_MARKER).write_bytes(b"incomplete")
    with pytest.raises(BackupError):
        verify_restored(manifest, destination)


def test_verify_restored_rejects_junction_and_untrusted_manifest_path(roots, tmp_path, monkeypatch):
    (roots["uploads"] / "a").write_bytes(b"data")
    archive = tmp_path / "backup.zip"
    summary = create_backup(roots, archive)
    manifest = verify_backup(archive, summary["archive_sha256"])
    destination = tmp_path / "restored"
    restore_backup(archive, destination, summary["archive_sha256"])
    original = Path.lstat
    linked = destination / "files/uploads"

    def lstat(path, *args, **kwargs):
        if path == linked:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(BackupError, match="linked_path"):
        verify_restored(manifest, destination)
    manifest["entries"][0]["path"] = "files/uploads/../../outside"
    with pytest.raises(BackupError, match="unsafe_archive_path"):
        verify_restored(manifest, destination)


def test_restore_rechecks_archive_hash_after_extraction(roots, tmp_path, monkeypatch):
    (roots["uploads"] / "a").write_bytes(b"data")
    archive = tmp_path / "backup.zip"
    summary = create_backup(roots, archive)
    original = backup._entry_hash
    changed = []

    def mutate(zipped, entry, output=None):
        original(zipped, entry, output)
        if output is not None and not changed:
            changed.append(True)
            with archive.open("ab") as stream:
                stream.write(b"changed after verification")

    monkeypatch.setattr(backup, "_entry_hash", mutate)
    destination = tmp_path / "restored"
    with pytest.raises(BackupError, match="archive_changed"):
        restore_backup(archive, destination, summary["archive_sha256"])
    assert (destination / backup.INCOMPLETE_MARKER).exists()
    assert not (destination / backup.RESTORE_REPORT).exists()


def test_restore_rejects_payload_changed_between_verification_and_extraction(
    roots, tmp_path, monkeypatch
):
    archive = tmp_path / "backup.zip"
    entries = [("files/uploads/a", b"first")]
    checksum = make_zip(archive, roots["uploads"], entries)
    replacement = tmp_path / "replacement.zip"
    make_zip(replacement, roots["uploads"], [("files/uploads/a", b"other")])
    original = backup._verify

    def replace_after_verify(stream, expected):
        manifest = original(stream, expected)
        archive.write_bytes(replacement.read_bytes())
        return manifest

    monkeypatch.setattr(backup, "_verify", replace_after_verify)
    destination = tmp_path / "restored"
    with pytest.raises(BackupError, match="entry_hash_mismatch"):
        restore_backup(archive, destination, checksum)
    assert (destination / backup.INCOMPLETE_MARKER).exists()
    assert not (destination / backup.RESTORE_REPORT).exists()


def test_payload_verification_uses_bounded_reads(roots, tmp_path, monkeypatch):
    (roots["uploads"] / "a").write_bytes(b"x" * (backup.CHUNK_SIZE + 7))
    archive = tmp_path / "backup.zip"
    summary = create_backup(roots, archive)
    original = zipfile.ZipExtFile.read
    reads = []

    def read(stream, size=-1):
        if stream.name != "manifest.json":
            reads.append(size)
            assert 0 < size <= backup.CHUNK_SIZE
        return original(stream, size)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", read)
    restore_backup(archive, tmp_path / "restored", summary["archive_sha256"])
    assert len(reads) >= 6
