from sqlalchemy import update

from api.routers.notices import bid_pipeline
from api.workspace.tables import workspaces


def test_original_form_work_survives_source_sync_and_never_implies_readiness(client, sqlite_engine):
    notice = "FORM-SYNC-TEST"
    client.post("/v2/notices", json={"notice_no": notice, "title": "Original form", "source": "MANUAL_E2E"})
    ws = client.post(f"/v2/notices/{notice}/initialize").json()
    filling = {"document_id": "source", "name": "Original.hwpx", "source_sha256": "a" * 64,
               "fields": [{"field_id": "f1", "value": "Draft with a reference"}],
               "input_version": 1, "review_status": "pending"}
    ws["inputs"]["form_fillings"] = [filling]
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).where(workspaces.c.notice_no == notice).values(inputs=ws["inputs"]))
        conn.execute(update(bid_pipeline).where(bid_pipeline.c.notice_no == notice).values(title="Changed source"))
    result = client.post(f"/v2/notices/{notice}/sync", json={"version": 1})
    assert result.status_code == 200, result.text
    latest = result.json()
    assert latest["version"] == 2
    assert latest["inputs"]["form_fillings"] == [filling]
    assert not latest["ready"]
    assert any("원본 양식" in message and "배치 검토" in message for message in latest["blockers"])
