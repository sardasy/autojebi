import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from api.auth import verify_api_key
from api.routers import workspace


@pytest.fixture
def page_client(tmp_path, monkeypatch):
    folder = tmp_path / "exports" / "job" / "draft-pages"
    folder.mkdir(parents=True)
    path = folder / "page-001.png"
    Image.new("RGB", (100, 150), "white").save(path)
    job = SimpleNamespace(status="succeeded", result={
        "artifact": str(folder.parent / "draft.hwp"),
        "pages": [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}],
    })
    monkeypatch.setattr(workspace, "get_job", lambda _: job)
    monkeypatch.setattr(workspace, "storage_root", lambda: tmp_path)
    app = FastAPI()
    app.include_router(workspace.router)
    workspace.install_error_handlers(app)
    app.dependency_overrides[verify_api_key] = lambda: None
    return TestClient(app), job, path


def test_page_returns_actual_png(page_client):
    client, _, path = page_client
    response = client.get("/v2/jobs/job/pages/1")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == path.read_bytes()


@pytest.mark.parametrize("number", [0, 2])
def test_page_rejects_invalid_number(page_client, number):
    client, _, _ = page_client
    assert client.get(f"/v2/jobs/job/pages/{number}").status_code == 404


def test_page_rejects_failed_job(page_client):
    client, job, _ = page_client
    job.status = "failed"
    assert client.get("/v2/jobs/job/pages/1").status_code == 404


def test_page_rejects_changed_file(page_client):
    client, _, path = page_client
    path.write_bytes(b"changed")
    assert client.get("/v2/jobs/job/pages/1").status_code == 409


def test_page_rejects_other_job_folder(page_client):
    client, job, path = page_client
    job.result["artifact"] = str(path.parent.parent.parent / "other" / "draft.hwp")
    assert client.get("/v2/jobs/job/pages/1").status_code == 409


def test_hwp_download_uses_binary_content_type(page_client):
    client, job, _ = page_client
    artifact = Path(job.result["artifact"])
    artifact.write_bytes(b"hwp-test-fixture")
    job.result["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    job.notice_no, job.input_version = "TEST", 1
    response = client.get("/v2/jobs/job/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-hwp"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.content == artifact.read_bytes()


def test_locked_hwp_download_gives_recovery_action(page_client, monkeypatch):
    client, job, _ = page_client
    artifact = Path(job.result["artifact"])
    artifact.write_bytes(b"hwp-test-fixture")

    def locked(_):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "read_bytes", locked)
    response = client.get("/v2/jobs/job/download")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "artifact_unreadable"
    assert "한글" in response.json()["detail"]["next_action"]
