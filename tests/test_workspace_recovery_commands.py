from pathlib import Path

import pytest
from sqlalchemy import select, update

from api.workspace.tables import jobs
from api.workspace.worker import run_once


@pytest.fixture
def recovery_workspace(client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    assert (
        client.post(
            "/v2/notices",
            json={"notice_no": "RECOVERY", "title": "Recovery", "source": "MANUAL", "raw": {}},
        ).status_code
        == 200
    )
    assert client.post("/v2/notices/RECOVERY/initialize").status_code == 200


def submit(client, kind="excel", key="first", version=1):
    return client.post(
        "/v2/notices/RECOVERY/jobs",
        json={"kind": kind, "input_version": version, "idempotency_key": key},
    )


def recover(client, job_id, **values):
    return client.post(
        f"/v2/jobs/{job_id}/recover",
        json={
            "version": 1,
            "idempotency_key": "recover",
            "note": "Checked failed result",
            **values,
        },
    )


def test_stale_review_rejected_without_changing_input_version(
    client, sqlite_engine, recovery_workspace
):
    job_id = submit(client).json()["id"]
    assert run_once(sqlite_engine)
    body = {
        "version": 1,
        "job_id": job_id,
        "action": "approved",
        "note": "First decision",
        "expected_review_id": None,
    }
    first = client.post("/v2/notices/RECOVERY/reviews", json=body)
    assert first.status_code == 200
    stale = client.post("/v2/notices/RECOVERY/reviews", json={**body, "action": "rejected"})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "review_conflict"
    last_id = next(r["id"] for r in first.json()["reviews"] if r["job_id"] == job_id)
    second = client.post(
        "/v2/notices/RECOVERY/reviews",
        json={**body, "action": "rejected", "expected_review_id": last_id},
    )
    assert second.status_code == 200
    assert second.json()["version"] == 1
    assert second.json()["reviews"][0]["action"] == "rejected"


def test_lost_artifact_recovery_preserves_original_and_packages_replacement(
    client, sqlite_engine, recovery_workspace
):
    original = submit(client).json()["id"]
    run_once(sqlite_engine)
    original_job = client.get(f"/v2/jobs/{original}").json()
    Path(original_job["result"]["artifact"]).unlink()
    normal = submit(client, key="another")
    assert normal.status_code == 409
    assert normal.json()["detail"]["code"] == "artifact_recovery_required"
    response = recover(client, original)
    assert response.status_code == 202, response.text
    replacement = response.json()["id"]
    assert replacement != original
    assert recover(client, original).json()["id"] == replacement
    assert recover(client, original, idempotency_key="double-click").json()["id"] == replacement
    assert run_once(sqlite_engine)
    assert client.get(f"/v2/jobs/{replacement}/download").status_code == 200
    assert client.get(f"/v2/jobs/{original}/download").status_code == 410
    package = submit(client, kind="package", key="package").json()["id"]
    assert run_once(sqlite_engine)
    packaged = client.get(f"/v2/jobs/{package}").json()
    assert packaged["status"] == "succeeded", packaged
    assert packaged["result"]["included_jobs"] == [replacement]
    assert client.get(f"/v2/jobs/{original}").json()["status"] == "succeeded"


def test_healthy_artifact_cannot_be_duplicated_as_recovery(
    client, sqlite_engine, recovery_workspace
):
    original = submit(client).json()["id"]
    run_once(sqlite_engine)
    assert recover(client, original).status_code == 409


def test_rejected_valid_artifact_can_be_regenerated_with_reason(
    client, sqlite_engine, recovery_workspace
):
    original = submit(client).json()["id"]
    run_once(sqlite_engine)
    assert (
        client.post(
            "/v2/notices/RECOVERY/reviews",
            json={"version": 1, "job_id": original, "action": "rejected", "note": "Review again"},
        ).status_code
        == 200
    )
    assert recover(client, original).status_code == 202


def test_uncertain_hwp_requires_explicit_confirmation_across_versions(
    client, sqlite_engine, recovery_workspace
):
    original = submit(client, kind="hwp").json()["id"]
    with sqlite_engine.begin() as conn:
        conn.execute(
            update(jobs)
            .where(jobs.c.id == original)
            .values(status="failed", error={"code": "interrupted"})
        )
    assert submit(client, kind="hwp", key="unsafe-retry").status_code == 409
    assert recover(client, original).json()["detail"]["code"] == "hwp_confirmation_required"
    assert (
        client.post(
            "/v2/notices/RECOVERY/decision",
            json={"version": 1, "decision": "hold", "note": "Check worker"},
        ).status_code
        == 200
    )
    assert submit(client, kind="hwp", key="unsafe-new-version", version=2).status_code == 409
    response = recover(client, original, version=2, external_state_confirmed=True)
    assert response.status_code == 202
    assert response.json()["input_version"] == 2
    assert response.json()["parameters"]["recovery_of"] == original
    with sqlite_engine.connect() as conn:
        records = conn.execute(select(jobs)).mappings().all()
        assert len([r for r in records if not r["parameters"].get("attempt_only")]) == 2
        assert all(r["status"] == "blocked" for r in records if r["parameters"].get("attempt_only"))


def test_running_job_cannot_be_recovered(client, recovery_workspace):
    original = submit(client).json()["id"]
    assert recover(client, original).status_code == 409


def test_recovery_key_conflicts_and_stale_versions_are_rejected(
    client, sqlite_engine, recovery_workspace
):
    original = submit(client).json()["id"]
    with sqlite_engine.begin() as conn:
        conn.execute(update(jobs).values(status="failed"))
    assert recover(client, original, version=999).status_code == 409
    assert recover(client, original).status_code == 202
    assert recover(client, original, note="Different request").status_code == 409


def test_hwp_preflight_rejection_is_audited_without_marking_com_uncertain(
    client, recovery_workspace
):
    response = submit(client, kind="hwp", version=999)
    assert response.status_code == 409
    job_id = response.json()["detail"]["job_id"]
    job = client.get(f"/v2/jobs/{job_id}").json()
    assert job["status"] == "blocked"
    assert job["parameters"]["attempt_only"] is True
    assert job["parameters"]["requested_input_version"] == 999
    assert submit(client, kind="hwp", key="valid").status_code == 202
