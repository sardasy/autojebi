from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


class PathViolation(ValueError):
    pass


def _plain_path(path: Path) -> None:
    # Resolve alone would conceal a symlink or Windows junction from the allowlist.
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise PathViolation("linked_path")


@dataclass(frozen=True)
class AllowedPaths:
    template_root: Path
    source_root: Path
    output_root: Path

    def __post_init__(self) -> None:
        for name in ("template_root", "source_root", "output_root"):
            root = Path(os.path.abspath(getattr(self, name)))
            _plain_path(root)
            if not root.is_dir():
                raise PathViolation("root_missing")
            object.__setattr__(self, name, root.resolve(strict=True))
        if self.output_root == self.template_root or self.output_root == self.source_root:
            raise PathViolation("output_root_must_be_distinct")

    def resolve(self, value: str, kind: str) -> Path:
        root = {
            "template": self.template_root,
            "source": self.source_root,
            "output": self.output_root,
        }[kind]
        if not value or "\x00" in value or value.startswith(("\\\\", "//")):
            raise PathViolation("invalid_path")
        candidate = Path(value)
        if ".." in candidate.parts or any(
            ":" in part for part in candidate.parts if part != candidate.anchor
        ) or (candidate.drive and not candidate.is_absolute()):
            raise PathViolation("invalid_path")
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.is_relative_to(root):
            raise PathViolation("path_outside_root")
        _plain_path(candidate)
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root) or resolved.suffix.lower() not in {".hwp", ".hwpx"}:
            raise PathViolation("invalid_document_path")
        if kind == "output":
            if resolved.exists():
                raise PathViolation("output_exists")
            # The calling workspace creates job directories. This service creates no arbitrary paths.
            if not resolved.parent.is_dir():
                raise PathViolation("output_parent_missing")
        elif not resolved.is_file() or resolved.stat().st_size > 50_000_000:
            raise PathViolation("source_missing_or_too_large")
        return resolved
