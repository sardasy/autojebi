import hashlib
import json
import zipfile

import pytest
from sqlalchemy import update

from api.workspace.document_drafts import proposal_sections
from api.workspace.hwp_layout import proposal_text
from api.workspace.tables import jobs, workspaces
from api.workspace.worker import run_once
from api.workspace.writing_plan import source_signature


@pytest.fixture
def draft_workspace(client, sqlite_engine, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    assert client.post("/v2/notices", json={"notice_no": "DRAFT", "title": "Draft test", "source": "MANUAL_E2E"}).status_code == 200
    ws = client.post("/v2/notices/DRAFT/initialize").json()
    ws["inputs"]["documents"] = [{"id": "ref", "name": "Previous writing", "role": "company_reference", "text": "Prior engineering work.", "confirmed": False}]
    ws["inputs"]["documents"].append({"id":"source", "name":"Notice", "role":"notice_source", "text":"Technical proposal"})
    ws["inputs"]["writing_plan"]={"source_signature":source_signature(ws["inputs"]), "items":[{"id":"qualitative", "title":"Technical proposal", "document_kind":"qualitative_proposal", "action":"write", "document_id":"source", "quote":"Technical proposal"}]}
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=ws["inputs"]))
    return {"version": 1, "draft_id": "qualitative", "idempotency_key": "save-1",
            "document_kind": "qualitative_proposal", "title": "Technical proposal",
            "text": "Draft body", "note": "Work in progress", "references": [], "web_references": []}


def test_draft_without_requirements_roundtrip_retry_and_stale_edit(client, draft_workspace):
    path = "/v2/notices/DRAFT/document-drafts"
    body = draft_workspace
    result = client.post(path, json=body)
    assert result.status_code == 200, result.text
    ws = result.json()
    section = ws["inputs"]["proposal_sections"][0]
    assert ws["version"] == 2 and not ws["ready"]
    assert section["document_kind"] == "qualitative_proposal"
    assert section["review_status"] == "pending" and section["evidence_ids"] == []
    assert client.post(path, json=body).json()["version"] == 2
    assert client.post(path, json={**body, "text": "different"}).status_code == 409
    assert client.post(path, json={**body, "idempotency_key": "save-2"}).status_code == 409
    edited = client.post(path, json={**body, "idempotency_key": "save-2", "version": 2, "text": "Edited body"}).json()
    assert edited["version"] == 3 and len(edited["inputs"]["proposal_sections"]) == 1
    downloaded = client.get(path + "/qualitative/download")
    assert downloaded.status_code == 200 and "Edited body" in downloaded.text
    assert downloaded.headers["content-type"].startswith("text/markdown")
    assert client.get(path + "/missing/download").status_code == 404


@pytest.mark.parametrize("patch", [
    {"text": " "}, {"title": " "}, {"draft_id": "../bad"},
    {"references": [{"document_id": "unknown", "quote": "Prior engineering work."}]},
    {"references": [{"document_id": "ref", "quote": "Fabricated quote"}]},
    {"web_references": [{"title": "x", "url": "javascript:alert(1)", "quote": "x"}]},
    {"web_references": [{"title": "x", "url": "https://secret:password@example.com", "quote": "x"}]},
])
def test_invalid_draft_is_not_saved(client, draft_workspace, patch):
    assert client.post("/v2/notices/DRAFT/document-drafts", json={**draft_workspace, **patch}).status_code == 422
    assert client.get("/v2/notices/DRAFT/workspace").json()["version"] == 1


def test_references_stay_unverified_and_download_keeps_sources(client, draft_workspace):
    body = {**draft_workspace, "references": [{"document_id": "ref", "quote": "Prior engineering work."}],
            "web_references": [{"title": "Manufacturer", "url": "https://example.com/spec", "quote": "Sample claim"}]}
    result = client.post("/v2/notices/DRAFT/document-drafts", json=body).json()
    section = result["inputs"]["proposal_sections"][0]
    assert section["references"][0]["input_version"] == 1
    assert section["web_references"][0]["verified"] is False
    assert not result["inputs"]["documents"][0]["confirmed"]
    response = client.post("/v2/notices/DRAFT/sections/qualitative/review", json={"version": 2, "approved": True, "note": "Review", "text": "No verification marker"})
    assert response.status_code == 409
    text = client.get("/v2/notices/DRAFT/document-drafts/qualitative/download").text
    assert "Prior engineering work." in text and "https://example.com/spec" in text and "검증필요" in text


def test_nonproposal_documents_not_mixed_into_hwp():
    inputs = {"proposal_sections": [{"text": "Legacy"}, {"document_kind": "qualitative_proposal", "text": "Proposal"}, {"document_kind": "bid_document", "text": "BID"}, {"document_kind": "other_document", "text": "OTHER"}]}
    assert len(proposal_sections(inputs)) == 2
    assert proposal_text(inputs) == "Legacy\n\nProposal"


def test_applying_generated_proposal_keeps_written_documents(client, draft_workspace, sqlite_engine):
    client.post("/v2/notices/DRAFT/document-drafts", json=draft_workspace)
    job = client.post("/v2/notices/DRAFT/jobs", json={"kind": "proposal", "input_version": 2, "idempotency_key": "generated"}).json()
    with sqlite_engine.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.id == job["id"]).values(status="succeeded", result={"sections": [{"id": "generated", "text": "Generated", "review_status": "pending", "evidence_ids": []}]}))
    response = client.post(f"/v2/notices/DRAFT/jobs/{job['id']}/apply", json={"version": 2})
    assert response.status_code == 200, response.text
    sections = response.json()["inputs"]["proposal_sections"]
    assert len(sections) == 2 and sections[0]["id"] == "qualitative"
    assert sections[0]["text"] == "Draft body"


def test_package_contains_separate_drafts_with_hashes(client, draft_workspace, sqlite_engine):
    with sqlite_engine.begin() as conn:
        from api.workspace import service
        state = service.load(conn, "DRAFT")
        state["inputs"]["writing_plan"]["items"][0]["document_kind"]="other_document"
        conn.execute(update(workspaces).values(inputs=state["inputs"]))
    ws = client.post("/v2/notices/DRAFT/document-drafts", json={**draft_workspace, "document_kind": "other_document"}).json()
    # This fixture has no on-disk reference files; package the document-only snapshot.
    with sqlite_engine.begin() as conn:
        inputs = ws["inputs"]
        inputs["documents"] = []
        conn.execute(update(workspaces).values(inputs=inputs))
    job = client.post("/v2/notices/DRAFT/jobs", json={"kind": "package", "input_version": 2, "idempotency_key": "package"}).json()
    run_once(sqlite_engine)
    result = client.get(f"/v2/jobs/{job['id']}").json()
    assert result["status"] == "succeeded", result
    with zipfile.ZipFile(result["result"]["artifact"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        entry = next(f for f in manifest["files"] if f.get("name", "").startswith("drafts/"))
        assert hashlib.sha256(archive.read(entry["name"])).hexdigest() == entry["sha256"]
        assert "Draft body" in archive.read(entry["name"]).decode()
        assert "proposal.txt" not in archive.namelist()
