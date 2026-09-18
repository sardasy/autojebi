from copy import deepcopy
from datetime import datetime

import pytest
from sqlalchemy import update

from api.routers.notices import bid_pipeline
from api.workspace import service
from api.workspace.errors import WorkspaceError
from api.workspace.provenance import proposal_coverage
from api.workspace.tables import jobs, workspaces


@pytest.fixture
def safety_workspace(client):
    assert (
        client.post(
            "/v2/notices",
            json={"notice_no": "SAFETY", "title": "Safety", "source": "MANUAL", "raw": {}},
        ).status_code
        == 200
    )
    result = client.post("/v2/notices/SAFETY/initialize")
    assert result.status_code == 200
    return result.json()


def complete_inputs() -> dict:
    requirements = [
        {
            "id": key,
            "text": key,
            "document_id": "source",
            "quote": key,
            "locator": "p1",
            "category": "technical",
            "mandatory": True,
            "proposed_value": key,
            "evidence_id": "evidence",
            "evidence_quote": key,
            "evidence_locator": "p1",
            "review_status": "accepted",
            "compliance": "meets",
        }
        for key in ("A", "B")
    ]
    return {
        "source_reviewed": True,
        "checklist": [],
        "documents": [
            {"id": "source", "role": "notice_source", "text": "A B"},
            {"id": "evidence", "role": "product_evidence", "text": "A B", "confirmed": True},
        ],
        "requirements": requirements,
        "proposal_sections": [
            {
                "id": "section",
                "text": "A B",
                "requirement_ids": ["A", "B"],
                "evidence_ids": ["evidence"],
                "review_status": "approved",
            }
        ],
    }


@pytest.mark.parametrize(
    "field,value",
    [("base_price", 123456), ("open_date", datetime(2026, 10, 1, 10)), ("source", "G2B_CORRECTED")],
)
def test_fact_change_blocks_jobs_and_sync_uses_corrected_column(
    client, sqlite_engine, safety_workspace, field, value
):
    with sqlite_engine.begin() as conn:
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == "SAFETY")
            .values(**{field: value})
        )
    ws = client.get("/v2/notices/SAFETY/workspace").json()
    assert ws["source_changed"] and not ws["ready"]
    response = client.post(
        "/v2/notices/SAFETY/jobs",
        json={"kind": "excel", "input_version": 1, "idempotency_key": "changed"},
    )
    assert response.status_code == 409
    synced = client.post("/v2/notices/SAFETY/sync", json={"version": 1}).json()
    assert not synced["source_changed"]
    actual = synced["inputs"]["notice"][field]
    if field == "open_date":
        assert actual.startswith("2026-10-01")
    else:
        assert actual == value


def test_normalized_columns_override_stale_raw():
    facts = service.notice_facts(
        {"base_price": 200, "org_name": "corrected", "raw": {"bssamt": 100, "ntceInsttNm": "old"}}
    )
    assert facts["base_price"] == 200
    assert facts["org_name"] == "corrected"


@pytest.mark.parametrize("mode", ["extract", "manual"])
def test_body_update_invalidates_acceptance_but_preserves_rejection(
    client, sqlite_engine, safety_workspace, mode
):
    inputs = {**safety_workspace["inputs"], **complete_inputs()}
    inputs["requirements"][1]["review_status"] = "rejected"
    with sqlite_engine.begin() as conn:
        conn.execute(
            update(workspaces).where(workspaces.c.notice_no == "SAFETY").values(inputs=inputs)
        )
    if mode == "extract":
        response = client.post(
            "/v2/notices/SAFETY/jobs",
            json={"kind": "extract", "input_version": 1, "idempotency_key": "extract"},
        )
        job_id = response.json()["id"]
        with sqlite_engine.begin() as conn:
            conn.execute(
                update(jobs)
                .where(jobs.c.id == job_id)
                .values(
                    status="succeeded",
                    result={
                        "documents": [{"id": "source", "text": "changed", "format": "pdf"}],
                        "warnings": [],
                    },
                )
            )
        result = client.post(f"/v2/notices/SAFETY/jobs/{job_id}/apply", json={"version": 1})
    else:
        result = client.post(
            "/v2/notices/SAFETY/documents/source/text",
            json={"version": 1, "text": "changed", "note": "Original checked"},
        )
    assert result.status_code == 200, result.text
    after = result.json()["inputs"]
    assert after["requirements"][0]["review_status"] == "pending"
    assert after["requirements"][1]["review_status"] == "rejected"
    assert after["proposal_sections"][0]["review_status"] == "pending"
    assert after["source_reviewed"] is False
    assert result.json()["blockers"]


def test_final_gate_revalidates_quotes_and_evidence_not_only_flags():
    inputs = complete_inputs()
    assert service.blockers(inputs) == []
    inputs["documents"][1]["text"] = "unrelated"
    assert any("필수 요구사항 검토" in issue for issue in service.blockers(inputs))
    inputs = complete_inputs()
    inputs["documents"][1]["confirmed"] = False
    assert service.blockers(inputs)


@pytest.mark.parametrize("changed", [False, True])
def test_extract_preserves_unaffected_reviews(client, sqlite_engine, safety_workspace, changed):
    inputs = {**safety_workspace["inputs"], **complete_inputs()}
    inputs["documents"].append({"id": "reference", "role": "company_reference", "text": "old"})
    for doc in inputs["documents"]:
        doc["text_origin"] = "pdf"
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).where(workspaces.c.notice_no == "SAFETY").values(inputs=inputs))
    job = client.post("/v2/notices/SAFETY/jobs", json={"kind": "extract", "input_version": 1, "idempotency_key": "same"}).json()
    with sqlite_engine.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.id == job["id"]).values(status="succeeded", result={
            "documents": [{"id": d["id"], "text": "updated" if changed and d["id"] == "reference" else d["text"], "format": "pdf"} for d in inputs["documents"]], "warnings": [],
        }))
    response = client.post(f"/v2/notices/SAFETY/jobs/{job['id']}/apply", json={"version": 1})
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["version"] == (2 if changed else 1)
    assert state["inputs"]["documents"][1]["confirmed"] is True
    assert state["inputs"]["source_reviewed"] is True
    assert all(r["review_status"] == "accepted" for r in state["inputs"]["requirements"])
    assert state["inputs"]["proposal_sections"][0]["review_status"] == "approved"


def test_document_change_only_invalidates_linked_sections():
    from api.workspace.provenance import invalidate_document_dependents

    before = complete_inputs()
    before["documents"].append({"id": "reference", "role": "company_reference", "text": "old"})
    before["proposal_sections"].append({"id": "linked", "review_status": "approved", "reference": {"document_id": "reference"}})
    after = deepcopy(before)
    after["documents"][-1]["text"] = "new"
    invalidate_document_dependents(before, after)
    assert after["proposal_sections"][0]["review_status"] == "approved"
    assert after["proposal_sections"][1]["review_status"] == "pending"


def test_extract_cached_text_checks_original_hash(tmp_path, monkeypatch):
    import hashlib

    from api.workspace.execution import extract

    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    path = tmp_path / "source.pdf"
    path.write_bytes(b"%PDF original")
    document = {"id": "source", "storage_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "text": "cached", "text_origin": "pdf"}
    document["extraction"] = {"version": 1, "complete": True, "pages": [{"page_no": 1, "method": "pdf_text", "status": "extracted", "review_required": False}]}
    result = extract({"snapshot": {"documents": [document]}})
    assert result["documents"][0]["text"] == "cached"
    path.write_bytes(b"%PDF modified")
    with pytest.raises(WorkspaceError) as exc:
        extract({"snapshot": {"documents": [document]}})
    assert exc.value.detail["code"] == "source_file_changed"


def test_missing_proposal_requirement_blocks_until_valid_evidence_exception():
    inputs = complete_inputs()
    inputs["proposal_sections"][0]["requirement_ids"] = ["A"]
    assert proposal_coverage(inputs)["missing_ids"] == ["B"]
    assert any("대응 누락: B" in issue for issue in service.blockers(inputs))
    inputs["requirements"][1].update(
        proposal_disposition="evidence_only",
        proposal_note="Manufacturer certificate is submitted separately",
    )
    assert service.blockers(inputs) == []
    assert proposal_coverage(inputs)["evidence_only_count"] == 1
    inputs["requirements"][1]["proposal_note"] = " "
    assert service.blockers(inputs)


def test_section_review_requires_valid_corresponding_requirement_evidence(
    client, sqlite_engine, safety_workspace
):
    inputs = {**safety_workspace["inputs"], **complete_inputs()}
    inputs["proposal_sections"][0]["review_status"] = "pending"
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=inputs))
    payload = {
        "version": 1,
        "text": "A B",
        "note": "Checked",
        "approved": True,
        "requirement_ids": ["unknown"],
        "evidence_ids": ["evidence"],
    }
    assert (
        client.post("/v2/notices/SAFETY/sections/section/review", json=payload).status_code == 409
    )
    payload["requirement_ids"] = ["A", "B"]
    response = client.post("/v2/notices/SAFETY/sections/section/review", json=payload)
    assert response.status_code == 200
    assert response.json()["proposal_coverage"]["covered_count"] == 2


def test_same_decision_does_not_create_new_input_version(client, safety_workspace):
    result = client.post(
        "/v2/notices/SAFETY/decision",
        json={"version": 1, "decision": "pending", "note": "No change"},
    )
    assert result.status_code == 200
    assert result.json()["version"] == 1


def test_invalidation_does_not_mutate_historical_snapshot():
    before = complete_inputs()
    after = deepcopy(before)
    after["documents"][0]["text"] = "changed"
    from api.workspace.provenance import invalidate_document_dependents

    invalidate_document_dependents(before, after)
    assert before["requirements"][0]["review_status"] == "accepted"
    assert after["requirements"][0]["review_status"] == "pending"


def test_reanalysis_apply_deduplicates_and_preserves_human_decisions(
    client, sqlite_engine, safety_workspace
):
    inputs = {**safety_workspace["inputs"], **complete_inputs()}
    inputs["requirements"][1]["review_status"] = "rejected"
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=inputs))
    response = client.post(
        "/v2/notices/SAFETY/jobs",
        json={"kind": "analyze", "input_version": 1, "idempotency_key": "reanalyze"},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    with sqlite_engine.begin() as conn:
        conn.execute(
            update(jobs)
            .where(jobs.c.id == job_id)
            .values(
                status="succeeded",
                result={"requirements": deepcopy(inputs["requirements"]), "warnings": []},
            )
        )
    result = client.post(f"/v2/notices/SAFETY/jobs/{job_id}/apply", json={"version": 1})
    assert result.status_code == 200
    assert result.json()["version"] == 1
    assert [r["review_status"] for r in result.json()["inputs"]["requirements"]] == [
        "accepted",
        "rejected",
    ]
