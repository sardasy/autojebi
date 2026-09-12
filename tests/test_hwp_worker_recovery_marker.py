"""No COM calls: durable marker, stopped-PID acknowledgement, and crash fault injection."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.hwp_worker import recovery
from api.hwp_worker.recovery import RecoveryGuard, RecoveryRequired, acknowledge


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def failed_marker(root: Path) -> RecoveryGuard:
    guard = RecoveryGuard(root)

    def fail():
        raise RuntimeError("SECRET provider input/path")

    with pytest.raises(RuntimeError, match="SECRET"):
        guard.run(fail)
    return guard


def test_available_does_not_create_files(tmp_path):
    guard = RecoveryGuard(tmp_path)
    assert guard.available()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("contents", [b"", b"{", b"[]", b"arbitrary marker"])
def test_any_existing_marker_blocks_execution(tmp_path, contents):
    guard = RecoveryGuard(tmp_path)
    guard.marker.write_bytes(contents)
    assert not guard.available()
    with pytest.raises(RecoveryRequired):
        guard.run(lambda: pytest.fail("must not execute"))
    assert guard.marker.read_bytes() == contents


def test_success_fsyncs_safe_marker_before_single_execution(tmp_path, monkeypatch):
    guard = RecoveryGuard(tmp_path)
    syncs, calls = [], []
    fsync = recovery.os.fsync

    def synced(fd):
        syncs.append(fd)
        fsync(fd)

    monkeypatch.setattr(recovery.os, "fsync", synced)

    def operation():
        calls.append(1)
        assert syncs and not guard.available()
        marker = json.loads(guard.marker.read_bytes())
        assert set(marker) == {"nonce", "pid", "started_at", "state"}
        assert marker["pid"] == os.getpid() and marker["state"] == "running"
        assert len(marker["nonce"]) == 32
        return {"SECRET output": "only returned"}

    assert guard.run(operation) == {"SECRET output": "only returned"}
    assert calls == [1] and guard.available()


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_all_exceptions_retain_failed_marker_without_replay(tmp_path, error, capsys):
    guard = RecoveryGuard(tmp_path)
    calls = []

    def operation():
        calls.append(1)
        raise error("SECRET provider input/path")

    with pytest.raises(error):
        guard.run(operation)
    original = guard.marker.read_bytes()
    assert json.loads(original)["state"] == "failed" and b"SECRET" not in original
    with pytest.raises(RecoveryRequired):
        RecoveryGuard(tmp_path).run(operation)
    assert calls == [1] and guard.marker.read_bytes() == original
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err


def test_two_instances_refuse_concurrent_execution_and_ack(tmp_path, monkeypatch):
    one, two = RecoveryGuard(tmp_path), RecoveryGuard(tmp_path)
    started, release = threading.Event(), threading.Event()
    monkeypatch.setattr(recovery, "process_is_running", lambda _: False)

    def operation():
        started.set()
        assert release.wait(3)
        return {"ok": True}

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(one.run, operation)
        try:
            assert started.wait(2)
            with pytest.raises(RecoveryRequired):
                two.run(lambda: pytest.fail("second operation"))
            with pytest.raises(RecoveryRequired, match="worker_still_active"):
                two.acknowledge("checked", checksum(one.marker))
        finally:
            release.set()
        assert running.result(timeout=2) == {"ok": True}
    assert one.available() and two.available()


def test_process_crash_retains_marker_and_second_process_refuses(tmp_path):
    script = """
import os
import sys
from pathlib import Path
from api.hwp_worker.recovery import RecoveryGuard, RecoveryRequired
guard = RecoveryGuard(Path(sys.argv[1]))
if sys.argv[2] == "crash":
    guard.run(lambda: os._exit(73))
else:
    try:
        guard.run(lambda: os._exit(99))
    except RecoveryRequired:
        sys.exit(74)
"""
    first = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), "crash"], capture_output=True, timeout=20
    )
    assert first.returncode == 73
    guard = RecoveryGuard(tmp_path)
    original = guard.marker.read_bytes()
    assert json.loads(original)["state"] == "running"
    second = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), "retry"], capture_output=True, timeout=20
    )
    assert second.returncode == 74 and guard.marker.read_bytes() == original


@pytest.mark.parametrize("fails", [False, True])
def test_never_removes_or_rewrites_another_nonce(tmp_path, fails):
    guard = RecoveryGuard(tmp_path)
    replacement = []

    def operation():
        data = json.loads(guard.marker.read_bytes())
        data["nonce"] = "a" * 32
        raw = json.dumps(data).encode()
        guard.marker.write_bytes(raw)
        replacement.append(raw)
        if fails:
            raise RuntimeError("operation failed")
        return {}

    with pytest.raises(RuntimeError):
        guard.run(operation)
    assert guard.marker.read_bytes() == replacement[0]


def test_failed_state_live_pid_still_requires_stopped_worker(tmp_path):
    guard = failed_marker(tmp_path)
    with pytest.raises(RecoveryRequired, match="worker_still_active"):
        acknowledge(tmp_path, checksum(guard.marker), "COM window checked")
    assert not guard.available()


def test_acknowledgement_requires_matching_hash_and_dead_pid(tmp_path, monkeypatch):
    guard = failed_marker(tmp_path)
    checks = []
    monkeypatch.setattr(recovery, "process_is_running", lambda pid: checks.append(pid) or False)
    original = guard.marker.read_bytes()
    with pytest.raises(RecoveryRequired, match="marker_hash_conflict"):
        acknowledge(tmp_path, "0" * 64, "checked")
    assert checks == [] and guard.marker.read_bytes() == original
    guard.acknowledge(" Window closed and files checked ", checksum(guard.marker))
    assert checks == [os.getpid()] and guard.available()
    audits = list((tmp_path / ".hwp-recovery").glob("*.json"))
    assert len(audits) == 1
    audit = json.loads(audits[0].read_bytes())
    assert audit["marker"] == json.loads(original)
    assert audit["marker_sha256"] == hashlib.sha256(original).hexdigest()
    assert audit["note"] == "Window closed and files checked" and audit["acknowledged_at"]
    assert audit["acknowledged_by_pid"] == os.getpid()


@pytest.mark.parametrize("note", ["", " ", "x" * 4001])
def test_acknowledgement_requires_note(tmp_path, monkeypatch, note):
    guard = failed_marker(tmp_path)
    monkeypatch.setattr(recovery, "process_is_running", lambda _: False)
    with pytest.raises(RecoveryRequired, match="recovery_note_required"):
        acknowledge(tmp_path, checksum(guard.marker), note)
    assert not guard.available()


def test_unknown_pid_status_refuses_ack(tmp_path, monkeypatch):
    guard = failed_marker(tmp_path)

    def unknown(_):
        raise RecoveryRequired("pid_status_unknown")

    monkeypatch.setattr(recovery, "process_is_running", unknown)
    with pytest.raises(RecoveryRequired, match="pid_status_unknown"):
        acknowledge(tmp_path, checksum(guard.marker), "checked")
    assert not guard.available()


def test_audit_failure_retains_marker(tmp_path, monkeypatch):
    guard = failed_marker(tmp_path)
    before = guard.marker.read_bytes()
    monkeypatch.setattr(recovery, "process_is_running", lambda _: False)

    def failure(*args):
        raise OSError("SECRET disk error")

    monkeypatch.setattr(recovery, "_atomic", failure)
    with pytest.raises(RecoveryRequired):
        acknowledge(tmp_path, checksum(guard.marker), "checked")
    assert guard.marker.read_bytes() == before


def test_hash_rechecked_after_audit_before_unlink(tmp_path, monkeypatch):
    guard = failed_marker(tmp_path)
    monkeypatch.setattr(recovery, "process_is_running", lambda _: False)
    atomic = recovery._atomic

    def changed(path, value):
        atomic(path, value)
        current = json.loads(guard.marker.read_bytes())
        current["nonce"] = "b" * 32
        guard.marker.write_text(json.dumps(current))

    monkeypatch.setattr(recovery, "_atomic", changed)
    with pytest.raises(RecoveryRequired, match="marker_hash_conflict"):
        acknowledge(tmp_path, checksum(guard.marker), "checked")
    assert json.loads(guard.marker.read_bytes())["nonce"] == "b" * 32


def test_fsync_failure_never_starts_operation(tmp_path, monkeypatch):
    guard = RecoveryGuard(tmp_path)

    def failure(_):
        raise OSError("SECRET disk failure")

    monkeypatch.setattr(recovery.os, "fsync", failure)
    with pytest.raises(RecoveryRequired):
        guard.run(lambda: pytest.fail("not durable yet"))
    assert not guard.available()


@pytest.mark.parametrize("error_code,expected", [(87, False), (5, None), (1234, None)])
def test_windows_pid_open_errors_fail_closed(monkeypatch, error_code, expected):
    def opening(rights, inherit, pid):
        assert rights == 0x00100000 and inherit is False and pid == 123
        raise OSError(error_code, "SECRET Windows detail")

    monkeypatch.setitem(sys.modules, "win32api", SimpleNamespace(OpenProcess=opening))
    monkeypatch.setitem(sys.modules, "win32event", SimpleNamespace())
    if expected is None:
        with pytest.raises(RecoveryRequired, match="pid_status_unknown"):
            recovery._windows_process_is_running(123)
    else:
        assert recovery._windows_process_is_running(123) is expected


@pytest.mark.parametrize("wait_result,expected", [(0, False), (258, True), (-1, None)])
def test_windows_pid_probe_closes_handle_and_refuses_unknown(monkeypatch, wait_result, expected):
    closed = []
    monkeypatch.setitem(
        sys.modules,
        "win32api",
        SimpleNamespace(
            OpenProcess=lambda *args: 42,
            CloseHandle=lambda handle: closed.append(handle),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "win32event",
        SimpleNamespace(
            WaitForSingleObject=lambda handle, timeout: wait_result,
        ),
    )
    if expected is None:
        with pytest.raises(RecoveryRequired, match="pid_status_unknown"):
            recovery._windows_process_is_running(123)
    else:
        assert recovery._windows_process_is_running(123) is expected
    assert closed == [42]
