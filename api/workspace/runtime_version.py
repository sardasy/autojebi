"""Startup code identity and cached disk comparisons; never reports source paths."""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

CHECK_SECONDS = 5
FULL_HASH_SECONDS = 60
MAX_FILES = 2_000
MAX_FILE_BYTES = 4_000_000
MAX_SOURCE_BYTES = 50_000_000


class CodeVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    loaded_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    disk_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    captured_at: datetime | None = None
    status: Literal["current", "mismatch", "unknown"] = "unknown"
    restart_required: bool = False


class ProcessVersion:
    """Capture once during import, never from the first health request.

    Stat scans are throttled and unchanged files reuse their digest. Periodic full
    hashing also catches replacements that preserve file size and timestamps.
    This describes the source set present at startup, not a live-module reload.
    """

    def __init__(self, source_root: Path) -> None:
        self._root = source_root
        self._lock = threading.Lock()
        self._last_check = float("-inf")
        self._last_hash = float("-inf")
        self._signature: tuple | None = None
        self._disk: str | None = None
        self._captured_at = datetime.now(UTC)
        self._loaded = self._current()

    def _files(self) -> list[tuple[str, Path]]:
        files = [("api/" + p.relative_to(self._root).as_posix(), p)
                 for p in self._root.rglob("*.py")]
        config = self._root.parent / "pyproject.toml"
        if config.is_file():
            files.append(("pyproject.toml", config))
        if not files or len(files) > MAX_FILES:
            raise ValueError("source_inventory_unavailable")
        if any(path.is_symlink() or not path.is_file() for _, path in files):
            raise ValueError("source_inventory_unavailable")
        return sorted(files)

    def _current(self) -> str | None:
        with self._lock:
            now = time.monotonic()
            if now - self._last_check < CHECK_SECONDS:
                return self._disk
            self._last_check = now
            try:
                files = self._files()
                signature = tuple((name, path.stat().st_size, path.stat().st_mtime_ns)
                                  for name, path in files)
                if signature == self._signature and now - self._last_hash < FULL_HASH_SECONDS:
                    return self._disk
                digest, total = hashlib.sha256(), 0
                for name, path in files:
                    with path.open("rb") as stream:
                        content = stream.read(MAX_FILE_BYTES + 1)
                    total += len(content)
                    if len(content) > MAX_FILE_BYTES or total > MAX_SOURCE_BYTES:
                        raise ValueError("source_size_limit")
                    encoded = name.encode("utf-8")
                    digest.update(len(encoded).to_bytes(4, "big"))
                    digest.update(encoded)
                    digest.update(hashlib.sha256(content).digest())
                # Never label a racing deployment as a consistent source set.
                after = tuple((name, path.stat().st_size, path.stat().st_mtime_ns)
                              for name, path in self._files())
                if after != signature:
                    raise ValueError("source_changed_during_check")
                self._signature = signature
                self._disk = digest.hexdigest()
                self._last_hash = now
            except (OSError, ValueError):
                self._disk, self._signature = None, None
            return self._disk

    def report(self) -> CodeVersion:
        current = self._current()
        status = ("unknown" if self._loaded is None or current is None else
                  "current" if self._loaded == current else "mismatch")
        return CodeVersion(loaded_fingerprint=self._loaded, disk_fingerprint=current,
                           captured_at=self._captured_at, status=status,
                           restart_required=status == "mismatch")


# api/__init__.py imports this before loading application modules. Worker health
# reuses this object, so editing code cannot silently replace its startup identity.
PROCESS_VERSION = ProcessVersion(Path(__file__).resolve().parents[1])


def with_runtime_health(value: dict) -> dict:
    """Add API/worker code diagnostics without changing queue availability/state."""
    api = PROCESS_VERSION.report()
    workers, diagnostics = {}, []
    if api.status != "current":
        diagnostics.append({"component": "api", "code": "code_changed" if api.restart_required
                            else "version_unknown", "restart_required": api.restart_required})
    lanes = value.get("lanes")
    sources = ({lane: lanes.get(lane, {}) for lane in ("local", "external")}
               if isinstance(lanes, dict) else {"all": value})
    for lane, health in sources.items():
        try:
            version = CodeVersion.model_validate(health.get("code_version"))
        except (ValidationError, ValueError):
            version = CodeVersion()
        status = version.status
        # A worker can run an internally consistent yet different checkout. Compare
        # its startup identity against the API's current source set as well.
        if (api.disk_fingerprint and version.loaded_fingerprint
                and api.disk_fingerprint != version.loaded_fingerprint):
            status = "mismatch"
        restart = status == "mismatch"
        workers[lane] = {**version.model_dump(mode="json"), "status": status,
                         "restart_required": restart}
        if status != "current":
            diagnostics.append({"component": f"worker:{lane}",
                                "code": "code_changed" if restart else "version_unknown",
                                "restart_required": restart})
    restart = any(item["restart_required"] for item in diagnostics)
    return {**value, "runtime": {
        "api": api.model_dump(mode="json"), "workers": workers,
        "status": "mismatch" if restart else "unknown" if diagnostics else "current",
        "restart_required": restart, "diagnostics": diagnostics,
    }}
