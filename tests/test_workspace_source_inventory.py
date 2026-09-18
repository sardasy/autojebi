"""All declared attachments must be accounted for; no downloads or live DB."""

import hashlib
from copy import deepcopy

import pytest
from sqlalchemy import select, update

from api.workspace import service
from api.workspace.models import WorkspaceRecord
from api.workspace.source_inventory import source_inventory, source_text_complete
from api.workspace.tables import jobs, reviews, workspaces

NOTICE = "INVENTORY"
BASE = f"/v2/notices/{NOTICE}"
URL1 = "https://www.g2b.go.kr/source1"
URL2 = "https://www.g2b.go.kr/source2"


def declared():
    return {
        "ntceSpecFileNm1": "spec.pdf",
        "ntceSpecDocUrl1": URL1,
        "ntceSpecFileNm2": "prices.xls",
        "ntceSpecDocUrl2": URL2,
    }


def document(doc_id="source", **extra):
    return {
        "id": doc_id,
        "name": "spec.pdf",
        "role": "notice_source",
        "text": "100 V",
        "sha256": "same-bytes",
        "confirmed": False,
        "attachment_index": 1,
        "attachment_url": URL1,
        **extra,
    }


@pytest.fixture
def workspace(client, sqlite_engine, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Source inventory/review must not download or invoke providers")

    monkeypatch.setattr("httpx.HTTPTransport.handle_request", forbidden)
    monkeypatch.setattr("anthropic.Anthropic", forbidden)
    assert (
        client.post(
            "/v2/notices",
            json={"notice_no": NOTICE, "title": "Inventory", "source": "MANUAL", "raw": declared()},
        ).status_code
        == 200
    )
    ws = client.post(f"{BASE}/initialize").json()
    ws["inputs"].update(
        source_reviewed=True,
        documents=[
            document(),
            document(
                "conversion",
                name="converted-prices.pdf",
                attachment_index=None,
                attachment_url=None,
                text_origin="manual_confirmed",
            ),
        ],
        requirements=[
            {
                "id": "req",
                "document_id": "conversion",
                "quote": "100 V",
                "text": "Rating",
                "category": "technical",
                "locator": "p1",
                "mandatory": True,
                "review_status": "accepted",
                "compliance": "meets",
            }
        ],
        proposal_sections=[
            {"id": "section", "text": "Manual section", "review_status": "approved"}
        ],
    )
    write_inputs(sqlite_engine, ws["inputs"])
    return ws


def write_inputs(engine, inputs):
    with engine.begin() as conn:
        conn.execute(
            update(workspaces).where(workspaces.c.notice_no == NOTICE).values(inputs=inputs)
        )


def source_review(client, version=1):
    return client.post(
        f"{BASE}/source-review",
        json={"version": version, "text": "Checked", "note": "All source attachments checked"},
    )


def link(client, document_id="conversion", **changes):
    return client.post(
        f"{BASE}/documents/{document_id}/source-link",
        json={
            "version": 1,
            "attachment_index": 2,
            "note": "Manually checked converted original",
            **changes,
        },
    )


def fetched(client, engine, documents, key="fetch"):
    response = client.post(
        f"{BASE}/jobs", json={"kind": "fetch", "input_version": 1, "idempotency_key": key}
    )
    assert response.status_code == 202, response.text
    record = response.json()
    with engine.begin() as conn:
        conn.execute(
            update(jobs)
            .where(jobs.c.id == record["id"])
            .values(
                status="succeeded",
                quality="normal",
                result={"documents": documents, "warnings": []},
            )
        )
    return record["id"]


def test_inventory_includes_all_ten_slots_unsupported_and_missing_urls():
    raw = {f"ntceSpecFileNm{i}": f"attachment{i}.xls" for i in range(1, 11)}
    raw["ntceSpecDocUrl1"] = URL1
    raw["ntceSpecFileNm4"] = "archive.zip"
    before = {"raw": raw, "documents": []}
    assert len(source_inventory(before)) == 10
    assert source_inventory(before)[3] == {
        "index": 4,
        "name": "archive.zip",
        "url": "",
        "document_ids": [],
        "state": "missing",
    }
    assert all(a["state"] == "missing" for a in source_inventory(before))
    assert source_inventory({"raw": None}) == []
    assert source_inventory({"raw": {"ntceSpecDocUrl1": "", "ntceSpecFileNm1": " "}}) == []


def test_inventory_url_only_and_name_alias():
    result = source_inventory({"raw": {"ntceSpecDocUrl1": URL1, "ntceSpecDocNm2": "legacy.xls"}})
    assert result[0]["name"] == "g2b-attachment-1.bin"
    assert result[1]["name"] == "legacy.xls" and result[1]["state"] == "missing"


@pytest.mark.parametrize(
    "extra",
    [
        {"attachment_index": None},
        {"attachment_index": True},
        {"attachment_index": "1"},
        {"attachment_index": 2},
        {"attachment_url": URL1 + "?wrong"},
        {"role": "company_evidence", "confirmed": True},
        {"role": "product_evidence"},
    ],
)
def test_wrong_binding_or_company_evidence_never_covers_source(extra):
    assert (
        source_inventory({"raw": declared(), "documents": [document(**extra)]})[0]["state"]
        == "missing"
    )


def test_matching_filename_and_hash_without_binding_are_not_provenance():
    doc = document()
    doc.pop("attachment_index")
    doc.pop("attachment_url")
    assert source_inventory({"raw": declared(), "documents": [doc]})[0]["document_ids"] == []


def test_url_less_slot_requires_explicit_url_field():
    doc = document(attachment_index=2)
    doc.pop("attachment_url")
    inputs = {"raw": {"ntceSpecFileNm2": "prices.xls"}, "documents": [doc]}
    assert source_inventory(inputs)[0]["state"] == "missing"
    doc["attachment_url"] = ""
    assert source_inventory(inputs)[0]["state"] == "ready"


def test_unread_original_can_be_covered_by_explicitly_linked_conversion():
    inputs = {"raw": declared(), "documents": [document(text=" "), document("converted")]}
    assert source_inventory(inputs)[0]["state"] == "ready"
    assert source_text_complete(inputs)
    inputs["documents"][1]["text"] = ""
    assert source_inventory(inputs)[0]["state"] == "unread"
    assert not source_text_complete(inputs)


def test_missing_xls_is_visible_and_blocks_source_review_and_ready(client, workspace):
    response = client.get(f"{BASE}/workspace")
    assert response.status_code == 200
    view = response.json()
    assert view["source_attachments"][1] == {
        "index": 2,
        "name": "prices.xls",
        "url": URL2,
        "document_ids": [],
        "state": "missing",
    }
    assert any("prices.xls" in text for text in view["blockers"])
    assert not view["ready"]
    denied = source_review(client)
    assert denied.status_code == 409 and "prices.xls" in denied.json()["detail"]["message"]


def test_unread_xls_blocks_source_review_with_filename(client, sqlite_engine, workspace):
    workspace["inputs"]["documents"].append(
        document("xls", name="prices.xls", attachment_index=2, attachment_url=URL2, text="")
    )
    write_inputs(sqlite_engine, workspace["inputs"])
    assert client.get(f"{BASE}/workspace").json()["source_attachments"][1]["state"] == "unread"
    denied = source_review(client)
    assert denied.status_code == 409 and "prices.xls" in denied.json()["detail"]["message"]


def test_manual_link_recovers_and_invalidates_approvals_without_autoapprove(
    client, sqlite_engine, workspace
):
    before = deepcopy(workspace["inputs"])
    response = link(client)
    assert response.status_code == 200, response.text
    ws = response.json()
    assert ws["source_attachments"][1]["state"] == "ready"
    assert ws["source_attachments"][1]["document_ids"] == ["conversion"]
    assert ws["version"] == 2 and not ws["inputs"]["source_reviewed"]
    doc = ws["inputs"]["documents"][1]
    assert doc["attachment_url"] == URL2 and doc["attachment_index"] == 2
    assert doc["text"] == before["documents"][1]["text"] and doc["confirmed"] is False
    assert ws["inputs"]["requirements"][0]["review_status"] == "pending"
    assert ws["inputs"]["requirements"][0]["compliance"] == "unassessed"
    assert ws["inputs"]["proposal_sections"][0]["review_status"] == "pending"
    assert link(client).status_code == 409
    assert source_review(client, version=2).status_code == 200
    with sqlite_engine.connect() as conn:
        history = (
            conn.execute(select(reviews).where(reviews.c.action == "source_link")).mappings().one()
        )
        assert history["details"]["previous_inputs"] == before


@pytest.mark.parametrize("role", ["company_evidence", "product_evidence"])
def test_company_document_cannot_be_linked(client, sqlite_engine, workspace, role):
    workspace["inputs"]["documents"][1]["role"] = role
    write_inputs(sqlite_engine, workspace["inputs"])
    response = link(client)
    assert response.status_code == 409
    assert client.get(f"{BASE}/workspace").json()["version"] == 1


@pytest.mark.parametrize(
    "index,status", [(0, 422), (11, 422), (1.5, 422), (True, 422), ("2", 422), (3, 409)]
)
def test_link_requires_declared_integer_slot(client, workspace, index, status):
    assert link(client, attachment_index=index).status_code == status


def test_link_requires_note_and_preserves_rejection(client, sqlite_engine, workspace):
    assert link(client, note=" ").status_code == 422
    workspace["inputs"]["requirements"][0]["review_status"] = "rejected"
    workspace["inputs"]["documents"][1]["review_status"] = "rejected"
    write_inputs(sqlite_engine, workspace["inputs"])
    after = link(client).json()["inputs"]
    assert after["requirements"][0]["review_status"] == "rejected"
    assert after["documents"][1]["review_status"] == "rejected"


def test_fetch_same_id_merges_only_attachment_fields_preserving_manual_content(
    client, sqlite_engine, workspace
):
    original = workspace["inputs"]["documents"][1]
    original.update(confirmed=True, review_status="rejected", custom_review="Preserve")
    write_inputs(sqlite_engine, workspace["inputs"])
    old = deepcopy(original)
    job_id = fetched(
        client,
        sqlite_engine,
        [
            document(
                "conversion",
                attachment_index=2,
                attachment_url=URL2,
                text="",
                name="prices.xls",
                confirmed=False,
            )
        ],
    )
    response = client.post(f"{BASE}/jobs/{job_id}/apply", json={"version": 1})
    assert response.status_code == 200, response.text
    doc = response.json()["inputs"]["documents"][1]
    assert doc == {**old, "attachment_index": 2, "attachment_url": URL2}
    assert response.json()["source_attachments"][1]["state"] == "ready"


def test_fetch_preserves_different_ids_same_bytes_and_company_evidence(
    client, sqlite_engine, workspace
):
    company = document("company", role="company_evidence", confirmed=True)
    workspace["inputs"]["documents"].append(company)
    write_inputs(sqlite_engine, workspace["inputs"])
    job_id = fetched(
        client, sqlite_engine, [document("xls", attachment_index=2, attachment_url=URL2)]
    )
    response = client.post(f"{BASE}/jobs/{job_id}/apply", json={"version": 1})
    assert response.status_code == 200, response.text
    docs = {d["id"]: d for d in response.json()["inputs"]["documents"]}
    assert len(docs) == 4 and docs["company"] == company
    assert docs["source"]["sha256"] == docs["xls"]["sha256"]
    assert response.json()["source_attachments"][1]["document_ids"] == ["xls"]


def test_fetch_cannot_annotate_existing_company_id_as_source(client, sqlite_engine, workspace):
    workspace["inputs"]["documents"][1]["role"] = "company_evidence"
    write_inputs(sqlite_engine, workspace["inputs"])
    job_id = fetched(
        client, sqlite_engine, [document("conversion", attachment_index=2, attachment_url=URL2)]
    )
    response = client.post(f"{BASE}/jobs/{job_id}/apply", json={"version": 1})
    assert response.status_code == 409
    assert client.get(f"{BASE}/workspace").json()["version"] == 1


def test_old_successful_fetch_remains_history_and_new_request_can_recover(
    client, sqlite_engine, workspace
):
    old_id = fetched(client, sqlite_engine, [], key="old-bug")
    body = {"kind": "fetch", "input_version": 1, "idempotency_key": "old-bug"}
    assert client.post(f"{BASE}/jobs", json=body).json()["id"] == old_id
    body["idempotency_key"] = "recover"
    new_id = client.post(f"{BASE}/jobs", json=body).json()["id"]
    assert new_id != old_id
    body["idempotency_key"] = "dedup-running"
    assert client.post(f"{BASE}/jobs", json=body).json()["id"] == new_id
    with sqlite_engine.connect() as conn:
        old = conn.execute(select(jobs).where(jobs.c.id == old_id)).mappings().one()
        assert old["status"] == "succeeded" and old["result"] == {"documents": [], "warnings": []}


def test_workspace_inventory_field_defaults_for_compatibility(workspace):
    legacy = {**workspace, "source_attachments": []}
    legacy.pop("source_attachments")
    assert WorkspaceRecord(**legacy).source_attachments == []


def test_complete_pending_fetch_is_returned_without_duplicate_download(client, sqlite_engine, workspace):
    old_id = fetched(client, sqlite_engine, [document("xls", attachment_index=2, attachment_url=URL2, text="")])
    response = client.post(f"{BASE}/jobs", json={
        "kind": "fetch", "input_version": 1, "idempotency_key": "new-key",
    })
    assert response.json()["id"] == old_id


def test_unlinked_unread_source_still_blocks_readable_conversion():
    inputs = {"raw": declared(), "documents": [document(), document("unlinked", text="",
              attachment_index=None, attachment_url=None)]}
    assert not source_text_complete(inputs)


def test_old_source_review_and_ready_package_cannot_bypass_missing_attachment(
    client, sqlite_engine, workspace, tmp_path, monkeypatch
):
    inputs = deepcopy(workspace["inputs"])
    # This regression targets attachment readiness, independently of the deadline gate.
    inputs["notice"]["close_date"] = "2099-01-01T10:00:00+09:00"
    inputs["documents"].append(document("evidence", role="product_evidence", confirmed=True))
    inputs["requirements"][0].update(evidence_id="evidence", evidence_quote="100 V",
                                      evidence_locator="p1", proposed_value="100 V")
    inputs["proposal_sections"][0].update(requirement_ids=["req"], evidence_ids=["evidence"])
    assert service.blockers(inputs) == ["공고 첨부 누락: prices.xls"]
    monkeypatch.setattr(service, "input_file_issues", lambda inputs: [])
    artifact = tmp_path / "historical-package.zip"
    artifact.write_bytes(b"historical artifact")
    result = {"artifact": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
              "warnings": []}
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=inputs, decision="participate"))
        ws = service.load(conn, NOTICE)
        excel = service.create_job_record(conn, ws, "excel", "historical-excel", {})
        package = service.create_job_record(conn, ws, "package", "historical-package", {})
        conn.execute(update(jobs).where(jobs.c.id == excel["id"]).values(status="succeeded", result=result))
        conn.execute(update(jobs).where(jobs.c.id == package["id"]).values(status="succeeded",
                     result={**result, "included_jobs": [excel["id"]]}))
        service.audit(conn, ws, "approved", "Old approval", {}, excel["id"])
        service.audit(conn, ws, "ready", "Old ready flag", {}, package["id"])
        review_id = conn.execute(select(reviews.c.id).where(reviews.c.job_id == package["id"])).scalar_one()
    view = client.get(f"{BASE}/workspace").json()
    assert view["inputs"]["source_reviewed"] is True and view["ready"] is False
    response = client.post(f"{BASE}/reviews", json={"version": 1, "action": "ready",
              "job_id": package["id"], "expected_review_id": review_id, "note": "Try again"})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "not_ready"
