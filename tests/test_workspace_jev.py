"""JEV queue/DB integration with no network or paid calls."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from api.config import settings
from api.db.tables import bid_pipeline
from api.decision.models import EngineDecision
from api.decision.tables import notice_decisions
from api.workspace.executors.jev import JevEngine
from api.workspace.tables import jobs, workspaces
from api.workspace.worker import run_once

PREFIX = "/v2/notices/TEST-JEV"


@pytest.fixture
def setup(client, sqlite_engine, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("WORKSPACE_AUTH_ENABLED", "false")
    monkeypatch.setattr(settings, "workspace_jev_enabled", True)
    monkeypatch.setattr(settings, "typesafe_api_key", "fictional-key")
    policy = tmp_path / "policy.yaml"
    policy.write_text(Path("config/company.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(settings, "workspace_jev_policy_path", str(policy))
    assert client.post("/v2/notices", json={"notice_no": "TEST-JEV", "title": "HIL HVDC TEST ONLY", "raw": {}}).status_code == 200
    ws = client.post(f"{PREFIX}/initialize").json()
    inputs = copy.deepcopy(ws["inputs"])
    inputs["documents"] = [
        {"id": "src", "name": "Test source", "role": "notice_source", "text": "HIL HVDC simulator", "confirmed": False},
        {"id": "ref", "name": "Private reference", "role": "company_reference", "text": "DO NOT SEND REFERENCE", "confirmed": False},
    ]
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).where(workspaces.c.notice_no == "TEST-JEV").values(inputs=inputs))
    calls = []

    def decide(self, notice, policy):
        calls.append(notice)
        values = {key: {"value": value, "confidence": 0.93, "probabilities": {value: 0.93, "other": 0.07}}
                  for key, value in [("product_family", "hil"), ("application", "hvdc"),
                                     ("company_relevance", "high"), ("bid_priority", "high")]}
        return EngineDecision(engine_name="jev", model_version="jev-test-resolved", policy_version=policy.policy_version, **values)

    monkeypatch.setattr(JevEngine, "decide", decide)
    return calls, policy


def post(client, key="one", version=1, **extra):
    context = client.get(f"{PREFIX}/classification").json()
    return client.post(f"{PREFIX}/jobs", json={"kind": "jev", "input_version": version,
                       "idempotency_key": key, "classification_hash": context["request_hash"], **extra})


def test_display_structure_does_not_reset_jev_hash_or_call_count(client, sqlite_engine, setup):
    calls, _ = setup
    before = client.get(f"{PREFIX}/classification").json()
    job = post(client).json()
    assert run_once(sqlite_engine, lane="external")
    with sqlite_engine.begin() as conn:
        ws = conn.execute(select(workspaces)).mappings().one()
        inputs = copy.deepcopy(ws["inputs"])
        inputs["documents"][0]["extraction"] = {"complete": True, "presentation": {"version": 1, "spans": []}}
        conn.execute(update(workspaces).values(inputs=inputs, version=2))
    after = client.get(f"{PREFIX}/classification").json()
    assert before["request_hash"] == after["request_hash"]
    assert post(client, "display-only", version=2).json()["id"] == job["id"]
    assert len(calls) == 1


def test_queue_to_saved_classification_does_not_approve(client, sqlite_engine, setup):
    calls, _ = setup
    before = client.get(f"{PREFIX}/workspace").json()
    job = post(client).json()
    assert job["execution_lane"] == "external"
    assert post(client, key="double-click").json()["id"] == job["id"]
    assert not run_once(sqlite_engine, lane="local")
    assert run_once(sqlite_engine, lane="external")
    assert len(calls) == 1 and "DO NOT SEND" not in calls[0].body
    result = client.get(f"{PREFIX}/classification").json()
    stored = result["history"][0]
    assert stored["status"] == "succeeded"
    assert stored["result"]["evaluation"]["decision"]["product_family"]["value"] == "hil"
    assert result["current_job_id"] == job["id"]
    assert stored["result"]["decision_id"]
    with sqlite_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(notice_decisions)) == 1
        assert conn.scalar(select(notice_decisions.c.product_family)) == "hil"
    after = client.get(f"{PREFIX}/workspace").json()
    for key in ["inputs", "version", "ready", "decision", "reviews"]:
        assert before[key] == after[key]
    assert post(client, key="again").json()["id"] == job["id"]
    assert not run_once(sqlite_engine, lane="external")
    assert client.post(f"{PREFIX}/jobs/{job['id']}/apply", json={"version": 1}).status_code == 409


def test_review_version_reuses_but_source_or_policy_change_does_not(client, sqlite_engine, setup):
    calls, policy = setup
    job = post(client).json()
    run_once(sqlite_engine)
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(version=2))
    assert post(client, "review-only", version=2).json()["id"] == job["id"]
    assert len(calls) == 1
    # Full policy content changes, even with the same declared policy_version.
    policy.write_text(policy.read_text(encoding="utf-8").replace("Direct match", "Exact match"), encoding="utf-8")
    assert client.get(f"{PREFIX}/classification").json()["current_job_id"] is None
    new = post(client, "policy-changed", version=2).json()
    assert new["id"] != job["id"]
    run_once(sqlite_engine)
    with sqlite_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(notice_decisions)) == 2
    ws = client.get(f"{PREFIX}/workspace").json()
    ws["inputs"]["documents"][0]["text"] += " Revised original."
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(version=3, inputs=ws["inputs"]))
    state = client.get(f"{PREFIX}/classification").json()
    assert state["current_job_id"] is None and len(state["history"]) == 2


@pytest.mark.parametrize("error", [TimeoutError("SECRET"), RuntimeError("Authorization SECRET")])
def test_failure_is_unevaluated_durable_and_never_retried(client, sqlite_engine, setup, monkeypatch, error):
    calls = []

    def fail_call(*args):
        calls.append(1)
        raise error

    monkeypatch.setattr(JevEngine, "decide", fail_call)
    job = post(client).json()
    run_once(sqlite_engine)
    state = client.get(f"{PREFIX}/classification")
    assert "SECRET" not in state.text
    failed = state.json()["history"][0]
    assert failed["status"] == "failed" and failed["result"] is None
    assert failed["error"]["code"] == "jev_unavailable"
    assert post(client, "retry").json()["id"] == job["id"]
    assert not run_once(sqlite_engine) and len(calls) == 1
    assert client.post(f"/v2/jobs/{job['id']}/recover", json={
        "version": 1, "idempotency_key": "recover", "note": "test",
    }).status_code == 409
    with sqlite_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(notice_decisions)) == 0


@pytest.mark.parametrize("change", ["version", "policy", "source"])
def test_change_during_call_blocks_persistence(client, sqlite_engine, setup, monkeypatch, change):
    _, policy = setup
    original = JevEngine.decide

    def racing(self, notice, company):
        result = original(self, notice, company)
        if change == "policy":
            policy.write_text(policy.read_text(encoding="utf-8").replace("Direct match", "Exact match"), encoding="utf-8")
        else:
            with sqlite_engine.begin() as conn:
                conn.execute(update(workspaces).values(version=2) if change == "version" else
                             update(bid_pipeline).values(title="Different notice"))
        return result

    monkeypatch.setattr(JevEngine, "decide", racing)
    post(client)
    run_once(sqlite_engine)
    with sqlite_engine.connect() as conn:
        assert conn.scalar(select(jobs.c.status)) == "blocked"
        assert conn.scalar(select(func.count()).select_from(notice_decisions)) == 0


def test_preflight_hash_version_and_disable_gates(client, sqlite_engine, setup, monkeypatch):
    assert post(client, classification_hash="0" * 64).status_code == 409
    assert post(client, version=2).status_code == 409
    monkeypatch.setattr(settings, "workspace_jev_enabled", False)
    assert post(client).status_code == 409
    state = client.get(f"{PREFIX}/classification").json()
    assert not state["visible"] and not state["enabled"]
    with sqlite_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(jobs)) == 0


def test_model_changes_do_not_reset_content_call_limit(client, sqlite_engine, setup, monkeypatch):
    for number in range(2):
        monkeypatch.setattr(settings, "typesafe_default_model", f"test-{number}")
        assert post(client, key=str(number)).status_code == 202
        run_once(sqlite_engine)
    monkeypatch.setattr(settings, "typesafe_default_model", "test-third")
    response = post(client, key="third")
    assert response.status_code == 409 and response.json()["detail"]["code"] == "jev_call_limit"


def test_writer_only_execution_and_server_actor(client, sqlite_engine, setup, monkeypatch):
    credentials = [{"id": role, "name": role, "role": role,
                    "token_sha256": hashlib.sha256((role + "-fixture-" + "x" * 40).encode()).hexdigest()}
                   for role in ["viewer", "writer", "reviewer", "approver"]]
    context = client.get(f"{PREFIX}/classification").json()
    monkeypatch.setenv("WORKSPACE_AUTH_ENABLED", "true")
    monkeypatch.setenv("WORKSPACE_AUTH_USERS", json.dumps(credentials))
    monkeypatch.setenv("WORKSPACE_AUTH_REGISTRY", "")
    for role in ["viewer", "reviewer", "approver", "writer"]:
        headers = {"Authorization": f"Bearer {role}-fixture-" + "x" * 40}
        assert client.get(f"{PREFIX}/classification", headers=headers).status_code == 200
        response = client.post(f"{PREFIX}/jobs", headers=headers, json={"kind": "jev",
                               "input_version": 1, "idempotency_key": role,
                               "classification_hash": context["request_hash"]})
        assert response.status_code == (202 if role == "writer" else 403), response.text
        if role == "writer":
            assert response.json()["parameters"]["actor"]["id"] == "writer"


def test_sdk_retry_is_disabled(monkeypatch):
    typesafe_sdk = pytest.importorskip("typesafe_sdk")

    captured = {}
    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", lambda **kwargs: captured.update(kwargs))
    JevEngine(api_key="fictional")._create_client()
    assert captured["retry"].max_retries == 0
