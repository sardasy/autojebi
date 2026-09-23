"""Ephemeral ZIP form targets. Original workspace documents are never duplicated."""

import hashlib
import json
from pathlib import PurePosixPath

from api.parsing.attachment_text import MAX_ARCHIVE_DEPTH, MAX_BYTES, MAX_ENTRIES, checked_archive
from api.workspace.errors import fail
from api.workspace.storage import source_path


def provenance(doc: dict) -> dict:
    return {key: doc[key] for key in (
        "parent_document_id", "container_sha256", "member_path", "member_hashes"
    ) if key in doc}


def archive_targets(doc: dict, notice_no: str) -> list[dict]:
    content = source_path(doc).read_bytes()
    if hashlib.sha256(content).hexdigest() != doc.get("sha256"):
        fail("form_source_changed", "ZIP 원본을 읽는 동안 파일이 변경되었습니다. 최신 원본을 확인하세요.")
    budget, entries = [MAX_BYTES], [MAX_ENTRIES]
    result = []

    def walk(data: bytes, path: list[str], hashes: list[str], depth: int) -> None:
        with checked_archive(data, budget, entries) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                suffix = PurePosixPath(entry.filename).suffix.lower()
                if suffix not in {".zip", ".hwpx", ".hwp"}:
                    continue
                member = archive.read(entry)
                checksum = hashlib.sha256(member).hexdigest()
                chain, chain_hashes = [*path, entry.filename], [*hashes, checksum]
                if suffix == ".zip":
                    if depth < MAX_ARCHIVE_DEPTH:
                        walk(member, chain, chain_hashes, depth + 1)
                    continue
                if suffix == ".hwpx":
                    # Charge XML/image expansion to the SAME budget as the outer containers.
                    with checked_archive(member, budget, entries):
                        pass
                identity = [notice_no, doc["id"], doc["sha256"], chain, chain_hashes]
                target_id = "zipform-" + hashlib.sha256(json.dumps(
                    identity, ensure_ascii=False, separators=(",", ":")
                ).encode()).hexdigest()
                result.append({"id": target_id, "name": " / ".join([doc["name"], *chain]),
                               "role": "notice_source", "sha256": checksum,
                               "parent_document_id": doc["id"], "container_sha256": doc["sha256"],
                               "member_path": chain, "member_hashes": chain_hashes,
                               "_content": member})

    walk(content, [], [], 0)
    return result


def resolve(inputs: dict, document_id: str) -> dict:
    for doc in inputs.get("documents", []):
        if doc.get("role") != "notice_source":
            continue
        if doc["id"] == document_id:
            return doc
        if document_id.startswith("zipform-") and str(doc.get("name", "")).lower().endswith(".zip"):
            for target in archive_targets(doc, str(inputs.get("notice", {}).get("notice_no") or "")):
                if target["id"] == document_id:
                    return target
    if document_id.startswith("zipform-"):
        fail("form_target_changed", "ZIP 원본이 변경되었습니다. 최신 작성 대상을 선택하세요.")
    fail("form_source_missing", "공고에 연결된 원본 양식을 선택하세요.", status=404)


def retired(inputs: dict, filling: dict) -> bool:
    if not filling.get("parent_document_id"):
        return False
    parent = next((d for d in inputs.get("documents", [])
                   if d["id"] == filling["parent_document_id"]), {})
    return parent.get("sha256") != filling.get("container_sha256")
