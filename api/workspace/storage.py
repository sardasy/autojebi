"""Workspace file storage: allowed roots, source integrity checks and output artifacts."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from api.services.uploads import base_dir
from api.workspace.errors import fail


def storage_root() -> Path:
    root = Path(os.getenv("WORKSPACE_DATA_DIR", "data/workspace")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def source_path(doc: dict) -> Path:
    path = Path(doc.get("storage_path") or "").resolve()
    if not any(path.is_relative_to(root) for root in (base_dir().resolve(), storage_root())):
        fail("unsafe_path", "허용된 원본 보관 폴더 밖의 파일입니다.")
    if not path.is_file():
        fail("file_missing", "원본 파일이 없습니다.", "파일을 다시 등록하세요.")
    if doc.get("sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != doc["sha256"]:
        fail(
            "source_file_changed",
            "원본 파일 내용이 변경되었습니다.",
            "새 버전으로 다시 등록하세요.",
        )
    return path


def artifact(path: Path, warnings: list[str], **extra: Any) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        fail("file_missing", "생성 파일을 확인할 수 없습니다.")
    return {
        "artifact": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
        "warnings": warnings,
        **extra,
    }
