"""Fail-closed COM crash marker. Acknowledgement requires a stopped owning worker."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import tempfile
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class RecoveryRequired(RuntimeError):
    """Contains a fixed diagnostic code only; never provider errors or input values."""


class _Marker(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    nonce: str = Field(pattern=r"^[0-9a-f]{32}$")
    pid: int = Field(gt=0)
    started_at: AwareDatetime
    state: Literal["running", "failed"]


_registry_lock = threading.Lock()
_locks: dict[Path, threading.Lock] = {}
_active: set[Path] = set()


def _root(root: Path) -> Path:
    try:
        root = Path(root).resolve(strict=True)
        if root.is_dir():
            return root
    except OSError:
        pass
    raise RecoveryRequired("invalid_root")


def _thread_lock(root: Path) -> threading.Lock:
    with _registry_lock:
        return _locks.setdefault(root, threading.Lock())


def _sync_directory(root: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _plain(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise RecoveryRequired("linked_recovery_path")


@contextmanager
def _mutation(root: Path, *, wait: bool = False) -> Iterator[None]:
    lock = _thread_lock(root)
    if not lock.acquire(blocking=wait):
        raise RecoveryRequired("marker_busy")
    fd = None
    try:
        path = root / ".hwp-recovery.lock"
        if os.path.lexists(path):
            _plain(path)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        # The OS releases this short metadata lock on process death; the marker remains.
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except OSError:
        raise RecoveryRequired("marker_io_or_lock_failed") from None
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            lock.release()


def _encode(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False).encode("utf-8")


def _exclusive(path: Path, value: dict) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_encode(value))
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


def _atomic(path: Path, value: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".hwp-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_encode(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read(path: Path) -> tuple[bytes, _Marker]:
    try:
        _plain(path)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16_384:
            raise RecoveryRequired("invalid_marker")
        data = path.read_bytes()
        return data, _Marker.model_validate_json(data)
    except (OSError, ValueError):
        raise RecoveryRequired("invalid_marker") from None


def _windows_process_is_running(pid: int) -> bool:
    try:
        import win32api
        import win32event
    except ImportError:
        raise RecoveryRequired("pid_status_unknown") from None
    try:
        handle = win32api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE, no termination rights.
    except Exception as exc:
        code = getattr(exc, "winerror", None)
        if code is None and exc.args:
            code = exc.args[0]
        if code == 87:  # ERROR_INVALID_PARAMETER: the nonzero PID no longer exists.
            return False
        raise RecoveryRequired("pid_status_unknown") from None
    try:
        result = win32event.WaitForSingleObject(handle, 0)
        if result == 0:
            return False
        if result == 258:
            return True
        raise RecoveryRequired("pid_status_unknown")
    except Exception:
        raise RecoveryRequired("pid_status_unknown") from None
    finally:
        try:
            win32api.CloseHandle(handle)
        except Exception:
            raise RecoveryRequired("pid_status_unknown") from None


def process_is_running(pid: int) -> bool:
    """Unknown/denied status refuses acknowledgement, including possible PID reuse."""
    if pid <= 0:
        raise RecoveryRequired("invalid_pid")
    if pid == os.getpid():
        return True
    if os.name == "nt":
        return _windows_process_is_running(pid)
    try:
        os.kill(pid, 0)  # Signal zero only probes existence; it sends no signal.
    except ProcessLookupError:
        return False
    except OSError:
        raise RecoveryRequired("pid_status_unknown") from None
    return True


class RecoveryGuard:
    def __init__(self, root: Path) -> None:
        self.root = _root(root)
        self.marker = self.root / ".hwp-active.json"

    def available(self) -> bool:
        try:
            self.marker.lstat()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return False

    def mark_uncertain(self) -> None:
        """Latch even if a late operation just removed its running marker."""
        with _mutation(self.root, wait=True):
            if self.marker.exists():
                _, marker = _read(self.marker)
                marker.state = "failed"
                _atomic(self.marker, marker.model_dump(mode="json"))
            else:
                marker = _Marker(nonce=uuid.uuid4().hex, pid=os.getpid(),
                                 started_at=datetime.now(UTC), state="failed")
                _exclusive(self.marker, marker.model_dump(mode="json"))

    def run(self, operation: Callable[[], dict]) -> dict:
        marker = _Marker(
            nonce=uuid.uuid4().hex,
            pid=os.getpid(),
            started_at=datetime.now(UTC),
            state="running",
        )
        with _mutation(self.root):
            if self.root in _active or not self.available():
                raise RecoveryRequired("recovery_required")
            _exclusive(self.marker, marker.model_dump(mode="json"))
            _active.add(self.root)
        try:
            try:
                result = operation()
            except BaseException:
                try:
                    with _mutation(self.root):
                        _, current = _read(self.marker)
                        if current.nonce == marker.nonce and current.pid == marker.pid:
                            current.state = "failed"
                            _atomic(self.marker, current.model_dump(mode="json"))
                except (RecoveryRequired, OSError):
                    pass  # Keep the original running marker if failure recording is unavailable.
                raise
            with _mutation(self.root):
                _, current = _read(self.marker)
                if current.nonce != marker.nonce or current.pid != marker.pid or current.state == "failed":
                    raise RecoveryRequired("marker_changed")
                self.marker.unlink()
                _sync_directory(self.root)
            return result
        finally:
            with _thread_lock(self.root):
                _active.discard(self.root)

    def acknowledge(self, note: str, expected_marker_sha256: str) -> None:
        acknowledge(self.root, expected_marker_sha256, note)


def acknowledge(root: Path, expected_hash: str, note: str) -> None:
    """Archive the exact marker before clearing it; operators must stop its worker first."""
    root = _root(root)
    if not isinstance(note, str) or not note.strip() or len(note) > 4000 or "\x00" in note:
        raise RecoveryRequired("recovery_note_required")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_hash):
        raise RecoveryRequired("marker_hash_required")
    with _mutation(root):
        if root in _active:
            raise RecoveryRequired("worker_still_active")
        path = root / ".hwp-active.json"
        data, marker = _read(path)
        checksum = hashlib.sha256(data).hexdigest()
        if not hmac.compare_digest(checksum, expected_hash.lower()):
            raise RecoveryRequired("marker_hash_conflict")
        if process_is_running(marker.pid):
            raise RecoveryRequired("worker_still_active")
        archive = root / ".hwp-recovery"
        archive.mkdir(mode=0o700, exist_ok=True)
        _plain(archive)
        audit = {
            "marker": marker.model_dump(mode="json"),
            "marker_sha256": checksum,
            "note": note.strip(),
            "acknowledged_at": datetime.now(UTC).isoformat(),
            "acknowledged_by_pid": os.getpid(),
        }
        _atomic(archive / (uuid.uuid4().hex + ".json"), audit)
        # Recheck after audit I/O as well as holding the interprocess metadata lock.
        latest, _ = _read(path)
        if not hmac.compare_digest(hashlib.sha256(latest).hexdigest(), checksum):
            raise RecoveryRequired("marker_hash_conflict")
        path.unlink()
        _sync_directory(root)
