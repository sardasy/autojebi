import copy
import hashlib
import json
import sys

import pytest
from sqlalchemy import update

from api.parsing.kordoc import ParsedDocument, compare_text
from api.services import kordoc_client
from api.workspace.executors.document_compare import compare
from api.workspace.tables import workspaces
from api.workspace.worker import run_once


def report(content=b"source", **updates):
    return dict(contract_version=1, engine_version="4.14.1",
                source_sha256=hashlib.sha256(content).hexdigest(), format="hwpx",
                page_mode="section", text="voltage 220 V", markdown="voltage 220 V",
                fragments=[], tables=[], warnings=[], review_required=True, verified=False) | updates


def test_comparison_is_not_accuracy_and_preserves_numbers():
    result = compare_text("220 V 220 V", "220 V 230 V")
    assert result["missing_token_count"] == result["added_token_count"] == 1
    assert result["missing_examples"] == ["220"]
    assert not result["verified"]
    assert compare_text("", "220")["state"] == "no_baseline"


@pytest.mark.parametrize("updates", [
    {"verified": True}, {"engine_version": "latest"}, {"warnings": ["COM_EMPTY"]},
    {"fragments": [{"locator": "blocks/0", "kind": "paragraph", "text": "x", "page": 1}]},
    {"fragments": [{"locator": "blocks/0", "kind": "table_cell", "text": "x", "row": 0, "col": 0}]},
])
def test_contract_rejects_unverified_provenance(updates):
    with pytest.raises(ValueError):
        ParsedDocument.model_validate(report(**updates))


def test_disabled_and_malformed_sources_never_start_node(monkeypatch):
    monkeypatch.setattr(kordoc_client, "_capture", lambda *a, **k: pytest.fail("launched"))
    monkeypatch.setenv("WORKSPACE_KORDOC_ENABLED", "false")
    with pytest.raises(kordoc_client.KordocError, match="kordoc_disabled"):
        kordoc_client.parse_document(b"bad", ".hwpx")
    monkeypatch.setenv("WORKSPACE_KORDOC_ENABLED", "true")
    with pytest.raises(kordoc_client.KordocError, match="source_structure_rejected"):
        kordoc_client.parse_document(b"bad", ".hwpx")


def test_adapter_requires_hash_and_passes_only_buffer(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_KORDOC_ENABLED", "true")
    monkeypatch.setattr(kordoc_client, "validate_hwp_content", lambda *a: None)
    monkeypatch.setattr(kordoc_client.shutil, "which", lambda _: sys.executable)
    package = tmp_path / "node_modules/kordoc/package.json"
    package.parent.mkdir(parents=True)
    package.write_text("{}")
    monkeypatch.setattr(kordoc_client, "RUNTIME", tmp_path)

    def capture(command, content, **kwargs):
        assert content == b"source"
        assert "--permission" in command
        assert not any("allow-child" in arg or "allow-fs-write" in arg for arg in command)
        return json.dumps(report(source_sha256="0" * 64)).encode()

    monkeypatch.setattr(kordoc_client, "_capture", capture)
    with pytest.raises(kordoc_client.KordocError, match="source_hash_mismatch"):
        kordoc_client.parse_document(b"source", ".hwpx")


@pytest.mark.parametrize(("script", "timeout", "code"), [
    ("import time; time.sleep(10)", 0.1, "parser_timeout"),
    ("import sys; sys.stdout.write('x'*5000000)", 5, "output_limit"),
    ("raise RuntimeError('SECRET')", 5, "parser_failed"),
])
def test_subprocess_limits_and_sanitized_errors(script, timeout, code):
    with pytest.raises(kordoc_client.KordocError, match=f"^{code}$"):
        kordoc_client._capture([sys.executable, "-c", script], b"", timeout=timeout)


def test_manual_job_preserves_inputs_and_cannot_apply(client, sqlite_engine, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKSPACE_KORDOC_ENABLED", "false")
    monkeypatch.setenv("WORKSPACE_AUTH_ENABLED", "false")
    prefix = "/v2/notices/TEST-KORDOC"
    assert client.post("/v2/notices", json={"notice_no": "TEST-KORDOC", "title": "Test", "raw": {}}).status_code == 200
    ws = client.post(f"{prefix}/initialize").json()
    assert ws["kordoc_comparison_enabled"] is False
    body = {"kind": "document_compare", "input_version": 1, "idempotency_key": "one"}
    assert client.post(f"{prefix}/jobs", json=body).status_code == 503
    monkeypatch.setenv("WORKSPACE_KORDOC_ENABLED", "true")
    source = tmp_path / "sample.hwp"
    source.write_bytes(b"source")
    inputs = copy.deepcopy(ws["inputs"])
    inputs["documents"] = [{"id": "src", "name": source.name, "role": "notice_source", "text": "voltage 200 V",
                            "storage_path": str(source), "sha256": hashlib.sha256(b"source").hexdigest(), "confirmed": True},
                           {"id": "private", "name": "private.hwpx", "role": "company_reference", "text": "PRIVATE"}]
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=inputs))
    calls = []

    def parse(content, suffix):
        calls.append(content)
        return ParsedDocument.model_validate(report(content))

    monkeypatch.setattr(kordoc_client, "parse_document", parse)
    before = client.get(f"{prefix}/workspace").json()
    assert before["kordoc_comparison_enabled"] is True
    job = client.post(f"{prefix}/jobs", json=body).json()
    assert job["execution_lane"] == "external"
    assert client.post(f"{prefix}/jobs", json=body).json()["id"] == job["id"]
    assert not run_once(sqlite_engine, lane="local")
    assert run_once(sqlite_engine, lane="external")
    after = client.get(f"{prefix}/workspace").json()
    result = next(j for j in after["jobs"] if j["id"] == job["id"])
    assert result["status"] == "succeeded", result
    assert len(result["result"]["comparisons"]) == 1
    assert result["result"]["comparisons"][0]["comparison_v2"]["summary"]["content"] == 1
    assert calls == [b"source"]
    for key in ["inputs", "version", "ready", "decision", "reviews"]:
        assert before[key] == after[key]
    assert client.post(f"{prefix}/jobs/{job['id']}/apply", json={"version": 1}).status_code == 409
    assert client.post(f"{prefix}/reviews", json={"version": 1, "job_id": job["id"],
                       "action": "approved", "note": "must reject"}).status_code == 409


def test_bad_source_is_isolated_and_reference_files_excluded(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_KORDOC_ENABLED", "true")
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    path = tmp_path / "source.hwp"
    path.write_bytes(b"source")
    doc = {"id": "good", "name": path.name, "role": "notice_source", "storage_path": str(path),
           "sha256": hashlib.sha256(b"source").hexdigest(), "text": "old"}
    monkeypatch.setattr(kordoc_client, "parse_document", lambda *a: ParsedDocument.model_validate(report()))
    result = compare({"input_version": 3, "snapshot": {"documents": [
        {**doc, "id": "bad", "sha256": "0" * 64}, doc,
        {**doc, "id": "private", "role": "company_evidence"},
    ]}})
    assert [item["status"] for item in result["comparisons"]] == ["failed", "compared"]
    assert result["comparisons"][0]["error_code"] == "source_hash_mismatch"
    assert not result["verified"]


def test_source_changed_during_parse_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_KORDOC_ENABLED", "true")
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    path = tmp_path / "source.hwpx"
    path.write_bytes(b"source")

    def parse(*args):
        path.write_bytes(b"changed")
        return ParsedDocument.model_validate(report())

    monkeypatch.setattr(kordoc_client, "parse_document", parse)
    result = compare({"input_version": 3, "snapshot": {"documents": [{"id": "source", "role": "notice_source",
                     "name": path.name, "storage_path": str(path), "sha256": hashlib.sha256(b"source").hexdigest()}]}})
    assert result["comparisons"][0]["error_code"] == "source_changed"
