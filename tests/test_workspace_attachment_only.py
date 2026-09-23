"""Reviewed attachment/electronic-only notices still require all non-HWP safety gates."""

import copy
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import update

from api.db.tables import bid_pipeline
from api.workspace import output_plan, service, writing_plan
from api.workspace.tables import workspaces
from api.workspace.worker import run_once
from tests.test_workspace_output_plan import prepared as prepared
from tests.test_workspace_safety import complete_inputs


def attachments_plan(inputs: dict) -> dict:
    return {"items": [
        {"id": "original", "title": "A", "document_id": "source", "quote": "A",
         "action": "attach", "document_kind": "other_document"},
        {"id": "electronic", "title": "B", "document_id": "source", "quote": "B",
         "action": "electronic", "document_kind": "bid_document"},
    ], "source_signature": writing_plan.source_signature(inputs), "note": "원문 제출 방식 확인"}


@pytest.fixture
def attachment_workspace(client, sqlite_engine, prepared):
    with sqlite_engine.begin() as conn:
        inputs = copy.deepcopy(service.load(conn, "OUTPUT-TEST")["inputs"])
        inputs["proposal_sections"] = []
        inputs["documents"][1]["item_id"] = "original"
        conn.execute(update(workspaces).values(inputs=inputs))
    response = client.put(prepared + "/writing-plan", json={"version": 1,
        "items": attachments_plan(inputs)["items"], "note": "원본 첨부와 전자 제출만 필요"})
    assert response.status_code == 200, response.text
    assert response.json()["writing_plan_current"] is True
    return prepared


def omit_hwp(client, prefix, version=2):
    return client.put(prefix + "/output-plan", json={"version": version,
        "template_keys": [], "note": "공고 확인: 별도 HWP 작성 불필요"})


def run_job(client, engine, prefix, version, kind):
    response = client.post(prefix + "/jobs", json={"kind": kind, "input_version": version,
                                                 "idempotency_key": service.uid()})
    assert response.status_code == 202, response.text
    assert run_once(engine)
    job = next(j for j in client.get(prefix + "/workspace").json()["jobs"]
               if j["id"] == response.json()["id"])
    assert job["status"] == "succeeded", job.get("error")
    return job


def test_reviewed_attachment_only_notice_reaches_ready_with_real_excel_and_sources(
    client, sqlite_engine, attachment_workspace,
):
    prefix = attachment_workspace
    state = omit_hwp(client, prefix).json()
    assert state["version"] == 3 and state["inputs"]["output_plan"]["template_keys"] == []
    assert state["blockers"] == [] and not state["ready"]
    excel = run_job(client, sqlite_engine, prefix, 3, "excel")
    pending = run_job(client, sqlite_engine, prefix, 3, "package")
    assert any("생성물 검토 승인 필요" in w for w in pending["result"]["warnings"])
    assert client.post(prefix + "/reviews", json={"version": 3, "job_id": pending["id"],
        "action": "ready", "note": "승인 전 차단 검증"}).status_code == 409
    assert client.post(prefix + "/reviews", json={"version": 3, "job_id": excel["id"],
        "action": "approved", "note": "원문과 Excel을 대조함"}).status_code == 200
    package = run_job(client, sqlite_engine, prefix, 3, "package")
    assert package["result"]["warnings"] == []
    assert package["result"]["included_jobs"] == [excel["id"]]
    with zipfile.ZipFile(package["result"]["artifact"]) as archive:
        assert "proposal.txt" not in archive.namelist()
        assert len([name for name in archive.namelist() if name.startswith("sources/")]) == 2
        assert [name for name in archive.namelist() if name.startswith("outputs/")] == [f"outputs/{excel['id']}.xlsx"]
        assert json.loads(archive.read("manifest.json"))["inputs"]["output_plan"]["template_keys"] == []
    result = client.post(prefix + "/reviews", json={"version": 3, "job_id": package["id"],
        "action": "ready", "note": "원본 첨부·Excel 검토 완료; 전자 제출은 담당자 수행"})
    assert result.status_code == 200, result.text
    assert client.get(prefix + "/workspace").json()["ready"] is True
    Path(excel["result"]["artifact"]).write_bytes(b"changed after approval")
    assert client.get(prefix + "/workspace").json()["ready"] is False


@pytest.mark.parametrize("invalid", ["missing", "empty", "stale", "write"])
def test_empty_plan_cannot_bypass_unreviewed_or_written_outputs(
    client, sqlite_engine, attachment_workspace, invalid,
):
    with sqlite_engine.begin() as conn:
        inputs = copy.deepcopy(service.load(conn, "OUTPUT-TEST")["inputs"])
        if invalid == "missing":
            inputs.pop("writing_plan")
        elif invalid == "empty":
            inputs["writing_plan"]["items"] = []
        elif invalid == "stale":
            inputs["writing_plan"]["source_signature"] = "old source"
        else:
            inputs["writing_plan"]["items"][0]["action"] = "write"
        conn.execute(update(workspaces).values(inputs=inputs))
    response = omit_hwp(client, attachment_workspace)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "written_outputs_required"
    assert "제안서 본문 작성 및 사실 확인 필요" in service.blockers(inputs)


def test_saved_empty_plan_is_invalidated_by_changed_source_or_new_write_target(
    client, sqlite_engine, attachment_workspace,
):
    prefix = attachment_workspace
    assert omit_hwp(client, prefix).status_code == 200
    changed = client.post(prefix + "/documents/source/text", json={"version": 3,
        "text": "A B C", "note": "원문 추가 요구 확인"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["writing_plan_current"] is False
    assert output_plan.template_keys(changed.json()["inputs"]) == ["bid_form", "proposal"]
    assert omit_hwp(client, prefix, 4).status_code == 422
    items = attachments_plan(changed.json()["inputs"])["items"]
    items.append({"id": "new", "title": "C", "document_id": "source", "quote": "C",
                  "action": "write", "document_kind": "qualitative_proposal"})
    updated = client.put(prefix + "/writing-plan", json={"version": 4, "items": items,
                                                         "note": "제안서 작성 대상 추가"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["writing_plan_current"] is True
    assert output_plan.template_keys(updated.json()["inputs"]) == ["bid_form", "proposal"]
    assert omit_hwp(client, prefix, 5).status_code == 422
    with sqlite_engine.begin() as conn:
        conn.execute(update(bid_pipeline).values(title="공식 공고 변경"))
    assert client.get(prefix + "/workspace").json()["source_changed"] is True
    assert omit_hwp(client, prefix, 5).status_code == 409


@pytest.mark.parametrize("missing", ["source_review", "requirement", "evidence", "attachment", "form"])
def test_attachment_only_keeps_source_evidence_requirement_and_form_gates(missing):
    inputs = complete_inputs()
    inputs["proposal_sections"] = []
    inputs["writing_plan"] = attachments_plan(inputs)
    inputs["output_plan"] = {"template_keys": [], "note": "공고 제출 방식 확인"}
    assert service.blockers(inputs) == []
    if missing == "source_review":
        inputs["source_reviewed"] = False
    elif missing == "requirement":
        inputs["requirements"][0]["compliance"] = "unassessed"
    elif missing == "evidence":
        inputs["documents"][1]["confirmed"] = False
    elif missing == "attachment":
        inputs["checklist"] = [{"id": "missing", "name": "필수 원본"}]
    else:
        inputs["form_fillings"] = [{"document_id": "source", "fields": [], "review_status": "pending"}]
    assert service.blockers(inputs)


def test_attachment_only_requires_explicit_output_selection_and_keeps_old_draft_review():
    inputs = complete_inputs()
    inputs["writing_plan"] = attachments_plan(inputs)
    assert output_plan.template_keys(inputs) == ["bid_form", "proposal"]
    inputs["proposal_sections"][0]["review_status"] = "pending"
    assert "제안서 본문 작성 및 사실 확인 필요" in service.blockers(inputs)
