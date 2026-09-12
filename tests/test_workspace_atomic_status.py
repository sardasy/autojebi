import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.workspace import receipts, supervisor


def test_atomic_status_retries_only_replacement_of_identical_payload(tmp_path, monkeypatch):
    target = tmp_path / "status.json"
    target.write_text('{"old": true}', encoding="utf-8")
    replace = receipts.os.replace
    attempts = []
    sleeps = []

    def transient(source, destination):
        attempts.append(source)
        if len(attempts) < 3:
            assert json.loads(target.read_text()) == {"old": True}
            raise PermissionError("simulated sharing violation")
        replace(source, destination)

    monkeypatch.setattr(receipts.os, "replace", transient)
    monkeypatch.setattr(receipts.time, "sleep", sleeps.append)
    receipts.atomic_json(target, {"new": True})
    assert len(set(attempts)) == 1 and len(attempts) == 3
    assert sleeps == [.02, .04]
    assert json.loads(target.read_text()) == {"new": True}


def test_persistent_replace_failure_is_bounded_and_keeps_previous_file(tmp_path, monkeypatch):
    target = tmp_path / "status.json"
    target.write_text("previous", encoding="utf-8")
    replace = Mock(side_effect=PermissionError("simulated persistent denial"))
    monkeypatch.setattr(receipts.os, "replace", replace)
    monkeypatch.setattr(receipts.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        receipts.atomic_json(target, {"new": True})
    assert replace.call_count == 5
    assert target.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [target]


def test_supervisor_keeps_monitoring_despite_status_storage_failure(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(supervisor, "atomic_json", Mock(side_effect=OSError("private storage detail")))
    count = 0
    stop = Mock()
    stop.is_set.side_effect = lambda: count >= 3
    child = SimpleNamespace(pid=123, returncode=1, poll=lambda: 1)

    def spawn(*args, **kwargs):
        nonlocal count
        count += 1
        return child

    supervisor.supervise(stop, spawn)
    assert count == 3
    assert "supervisor_status_write_failed" in caplog.text
    assert "private storage detail" not in caplog.text
