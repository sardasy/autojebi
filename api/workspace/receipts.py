"""Local completion journal and sanitized worker health, shared through WORKSPACE_DATA_DIR."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.workspace.runtime_version import PROCESS_VERSION, CodeVersion


def data_root() -> Path:
    return Path(os.getenv("WORKSPACE_DATA_DIR", "data/workspace")).resolve()


def sync_directory(path: Path) -> None:
    # Windows supports file fsync + atomic replace, but not POSIX directory fsync.
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_json(path: Path, value: dict) -> None:
    payload = json.dumps(value, ensure_ascii=True, allow_nan=False).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers/indexers can temporarily deny replacing an otherwise writable file.
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * 2**attempt)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    job_id: str = Field(min_length=1, max_length=36)
    claim_token: str = Field(min_length=1, max_length=36)
    notice_no: str = Field(min_length=1)
    input_version: int = Field(ge=1)
    status: Literal["succeeded", "blocked", "failed"]
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    completed_at: datetime
    lane: Literal["all", "local", "external"] = "all"

    def filename(self) -> str:
        key = json.dumps([self.job_id, self.claim_token]).encode()
        return hashlib.sha256(key).hexdigest() + ".json"


def save(receipt: Receipt) -> Path:
    root = data_root() / "receipts"
    path = (root if receipt.lane == "all" else root / receipt.lane) / receipt.filename()
    atomic_json(path, receipt.model_dump(mode="json"))
    return path


def pending(lane: str = "all") -> list[Path]:
    from api.workspace.lanes import validate_lane
    root = data_root() / "receipts"
    return sorted((root if validate_lane(lane) == "all" else root / lane).glob("*.json"))


def read(path: Path) -> Receipt:
    if path.is_symlink() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("invalid_receipt")
    receipt = Receipt.model_validate_json(path.read_bytes())
    if path.name != receipt.filename() or receipt.completed_at.tzinfo is None:
        raise ValueError("invalid_receipt")
    if (receipt.status == "succeeded") != (receipt.error is None):
        raise ValueError("invalid_receipt")
    return receipt


def quarantine(path: Path) -> None:
    target = path.parent / "quarantine"
    target.mkdir(exist_ok=True)
    # Never incorporate receipt contents or an untrusted filename into diagnostics.
    name = hashlib.sha256(os.fsencode(path.name)).hexdigest()
    os.replace(path, target / (name + ".invalid"))
    sync_directory(target)
    sync_directory(path.parent)


def remove(path: Path) -> None:
    path.unlink(missing_ok=True)
    sync_directory(path.parent)


FailureCode = Literal[
    "database_failure",
    "completion_pending",
    "unlock_failure",
    "storage_failure",
    "invalid_receipt",
    "runtime_failure",
]


class Failure(BaseModel):
    code: FailureCode
    at: datetime


class Health(BaseModel):
    schema_version: Literal[1] = 1
    pid: int
    heartbeat_at: datetime
    state: Literal[
        "starting", "idle", "recovering", "executing", "persisting", "retrying", "stopped"
    ]
    last_failure: Failure | None = None
    code_version: CodeVersion | None = None


def read_health(lane: str = "all") -> dict | None:
    """API-safe snapshot; consumers must check heartbeat age as well as state."""
    try:
        from api.workspace.lanes import validate_lane
        name = "worker-health.json" if validate_lane(lane) == "all" else f"worker-health-{lane}.json"
        health = Health.model_validate_json((data_root() / name).read_bytes())
        return health.model_dump(mode="json")
    except (OSError, ValueError, ValidationError):
        return None


class RuntimeHealth:
    def __init__(self, lane: str = "all") -> None:
        from api.workspace.lanes import validate_lane
        self.lane = validate_lane(lane)
        previous = read_health(lane)
        self.value = Health(
            pid=os.getpid(),
            heartbeat_at=datetime.now(UTC),
            state="starting",
            last_failure=previous.get("last_failure") if previous else None,
            code_version=PROCESS_VERSION.report(),
        )
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def record(self, state: str | None = None, failure: FailureCode | None = None) -> None:
        with self._lock:
            self.value.heartbeat_at = datetime.now(UTC)
            self.value.code_version = PROCESS_VERSION.report()
            if state is not None:
                self.value.state = state
            if failure:
                self.value.last_failure = Failure(code=failure, at=datetime.now(UTC))
            try:
                name = "worker-health.json" if self.lane == "all" else f"worker-health-{self.lane}.json"
                atomic_json(data_root() / name, self.value.model_dump(mode="json"))
            except OSError:
                self.value.last_failure = Failure(code="storage_failure", at=datetime.now(UTC))

    def _heartbeat(self) -> None:
        while not self._stop.wait(5):
            self.record()

    def start(self) -> None:
        self.record()
        self._thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        self.record("stopped")
