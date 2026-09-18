import json
import os
from pathlib import Path

from api.workspace import receipts, runtime_version


def source_tree(tmp_path):
    root = tmp_path / "api"
    root.mkdir()
    (root / "worker.py").write_text("VERSION = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test-only"\n', encoding="utf-8")
    return root


def test_startup_identity_survives_edits_before_first_health_construction(tmp_path, monkeypatch):
    root = source_tree(tmp_path)
    clock = [0.0]
    monkeypatch.setattr(runtime_version.time, "monotonic", lambda: clock[0])
    version = runtime_version.ProcessVersion(root)
    original = version.report().loaded_fingerprint
    (root / "worker.py").write_text("VERSION = 222\n", encoding="utf-8")
    clock[0] = 6
    monkeypatch.setattr(receipts, "PROCESS_VERSION", version)
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path / "runtime"))
    health = receipts.RuntimeHealth("local")
    health.record("idle")
    report = receipts.read_health("local")["code_version"]
    assert report["loaded_fingerprint"] == original
    assert report["disk_fingerprint"] != original
    assert report["status"] == "mismatch" and report["restart_required"]
    assert receipts.read_health("local")["state"] == "idle"


def test_fingerprint_ignores_env_data_and_absolute_checkout_path(tmp_path, monkeypatch):
    root = source_tree(tmp_path)
    clock = [0.0]
    monkeypatch.setattr(runtime_version.time, "monotonic", lambda: clock[0])
    version = runtime_version.ProcessVersion(root)
    before = version.report().loaded_fingerprint
    (tmp_path / ".env").write_text("API_KEY=SECRET_NEVER_EXPOSE\n", encoding="utf-8")
    (root / "data.json").write_text('{"private": "SECRET_NEVER_EXPOSE"}', encoding="utf-8")
    clock[0] = 61
    report = version.report()
    assert report.loaded_fingerprint == report.disk_fingerprint == before
    encoded = report.model_dump_json()
    assert "SECRET_NEVER_EXPOSE" not in encoded and str(tmp_path) not in encoded
    other = tmp_path / "other"
    other.mkdir()
    clone = source_tree(other)
    assert runtime_version.ProcessVersion(clone).report().loaded_fingerprint == before


def test_disk_hash_is_cached_but_periodically_rechecks_same_metadata(tmp_path, monkeypatch):
    root = source_tree(tmp_path)
    clock = [0.0]
    monkeypatch.setattr(runtime_version.time, "monotonic", lambda: clock[0])
    version = runtime_version.ProcessVersion(root)
    opened = []
    original_open = Path.open
    def record_open(path, *args, **kwargs):
        opened.append(path.name)
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", record_open)
    version.report()
    clock[0] = 6
    version.report()
    assert opened == []
    path = root / "worker.py"
    stamp = path.stat()
    path.write_text("VERSION = 2\n", encoding="utf-8")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    clock[0] = 61
    assert version.report().status == "mismatch"


def test_added_source_and_changed_dependency_config_require_restart(tmp_path, monkeypatch):
    root = source_tree(tmp_path)
    clock = [0.0]
    monkeypatch.setattr(runtime_version.time, "monotonic", lambda: clock[0])
    version = runtime_version.ProcessVersion(root)
    (root / "new_route.py").write_text("ENABLED = True\n", encoding="utf-8")
    clock[0] = 6
    assert version.report().restart_required
    restarted = runtime_version.ProcessVersion(root)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "new-test-only"\n', encoding="utf-8")
    clock[0] = 12
    assert restarted.report().restart_required


def test_unknown_startup_never_claims_later_files_were_loaded(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(runtime_version.time, "monotonic", lambda: clock[0])
    version = runtime_version.ProcessVersion(tmp_path / "api")
    source_tree(tmp_path)
    clock[0] = 6
    report = version.report()
    assert report.loaded_fingerprint is None and report.disk_fingerprint
    assert report.status == "unknown" and not report.restart_required


def test_api_worker_mismatch_is_a_warning_without_changing_availability(monkeypatch):
    api = runtime_version.CodeVersion(loaded_fingerprint="a" * 64, disk_fingerprint="b" * 64,
                                     status="mismatch", restart_required=True)
    worker = runtime_version.CodeVersion(loaded_fingerprint="c" * 64, disk_fingerprint="c" * 64,
                                        status="current")
    monkeypatch.setattr(runtime_version.PROCESS_VERSION, "report", lambda: api)
    health = {"available": True, "state": "executing", "lanes": {
        "local": {"code_version": worker.model_dump(mode="json")},
        "external": {},
    }}
    output = runtime_version.with_runtime_health(health)
    assert output["available"] and output["state"] == "executing"
    assert output["runtime"]["status"] == "mismatch"
    assert output["runtime"]["workers"]["local"]["restart_required"]
    assert output["runtime"]["workers"]["external"]["status"] == "unknown"
    assert {d["component"] for d in output["runtime"]["diagnostics"]} == {
        "api", "worker:local", "worker:external",
    }
    assert "runtime" not in health
    json.dumps(output)


def test_health_preserves_legacy_records_without_inventing_a_version(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    receipts.atomic_json(tmp_path / "worker-health.json", {
        "schema_version": 1, "pid": 123, "heartbeat_at": "2026-09-13T00:00:00+00:00",
        "state": "idle", "last_failure": None,
    })
    value = receipts.read_health()
    assert value["state"] == "idle" and value["code_version"] is None
    assert runtime_version.with_runtime_health(value)["runtime"]["workers"]["all"]["status"] == "unknown"


def test_api_package_captures_the_shared_version_during_import():
    import api

    assert api.PROCESS_VERSION is runtime_version.PROCESS_VERSION


def test_worker_health_endpoint_reports_api_and_lane_versions(client, monkeypatch):
    from datetime import UTC, datetime

    api = runtime_version.CodeVersion(loaded_fingerprint="a" * 64, disk_fingerprint="b" * 64,
                                     status="mismatch", restart_required=True)
    old_worker = runtime_version.CodeVersion(loaded_fingerprint="a" * 64, disk_fingerprint="b" * 64,
                                            status="mismatch", restart_required=True)
    current_worker = runtime_version.CodeVersion(loaded_fingerprint="b" * 64, disk_fingerprint="b" * 64,
                                                status="current")
    monkeypatch.setattr(runtime_version.PROCESS_VERSION, "report", lambda: api)
    def health(lane="all"):
        return {"pid": 123, "state": "idle", "heartbeat_at": datetime.now(UTC).isoformat(),
                "last_failure": None,
                "code_version": (old_worker if lane == "local" else current_worker).model_dump(mode="json")}
    monkeypatch.setattr(receipts, "read_health", health)
    response = client.get("/v2/worker/health")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["runtime"]["api"]["loaded_fingerprint"] == "a" * 64
    assert body["runtime"]["api"]["disk_fingerprint"] == "b" * 64
    assert body["runtime"]["workers"]["local"]["restart_required"] is True
    assert body["runtime"]["workers"]["external"]["restart_required"] is False
    assert body["runtime"]["diagnostics"] == [
        {"component": "api", "code": "code_changed", "restart_required": True},
        {"component": "worker:local", "code": "code_changed", "restart_required": True},
    ]
