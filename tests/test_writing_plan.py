import pytest
from sqlalchemy import update

from api.workspace.tables import workspaces


@pytest.fixture
def plan_workspace(client,sqlite_engine):
    client.post("/v2/notices",json={"notice_no":"PLAN","title":"Plan test","source":"MANUAL_E2E"})
    ws=client.post("/v2/notices/PLAN/initialize").json()
    ws["inputs"]["documents"]=[{"id":"source","role":"notice_source","name":"공고문", "text":"정성제안서 1부\n사업자등록증 1부", "confirmed":False}]
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=ws["inputs"]))
    return {"version":1,"note":"공고 검토 완료","items":[{"id":"proposal","title":"정성제안서","document_kind":"qualitative_proposal","action":"write","document_id":"source","quote":"정성제안서 1부"}]}


def test_review_required_then_only_confirmed_target_can_be_written(client,plan_workspace):
    draft={"version":1,"draft_id":"proposal","title":"정성제안서","document_kind":"qualitative_proposal","text":"검토 초안","note":"작성","idempotency_key":"first"}
    assert client.post("/v2/notices/PLAN/document-drafts",json=draft).status_code==409
    response=client.put("/v2/notices/PLAN/writing-plan",json=plan_workspace)
    assert response.status_code==200,response.text
    assert response.json()["writing_plan_current"] is True
    assert response.json()["ready"] is False
    assert not response.json()["inputs"]["source_reviewed"]
    assert client.post("/v2/notices/PLAN/document-drafts",json={**draft,"version":2,"draft_id":"not-reviewed"}).status_code==409
    assert client.post("/v2/notices/PLAN/document-drafts",json={**draft,"version":2}).status_code==200


@pytest.mark.parametrize("patch",[{"quote":"없는 원문"},{"document_id":"unknown"},{"title":"일반 목차"},{"title":"사업자등록증","quote":"사업자등록증 1부"}])
def test_source_or_issued_document_invalid(client,plan_workspace,patch):
    plan_workspace["items"][0].update(patch)
    assert client.put("/v2/notices/PLAN/writing-plan",json=plan_workspace).status_code==422


def test_source_change_invalidates_plan_without_deleting_draft(client,plan_workspace,sqlite_engine):
    client.put("/v2/notices/PLAN/writing-plan",json=plan_workspace)
    ws=client.post("/v2/notices/PLAN/document-drafts",json={"version":2,"draft_id":"proposal","title":"정성제안서","document_kind":"qualitative_proposal","text":"보존할 초안","note":"작성","idempotency_key":"one"}).json()
    ws["inputs"]["documents"][0]["text"]+="\n원문 변경"
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=ws["inputs"]))
    updated=client.get("/v2/notices/PLAN/workspace").json()
    assert updated["writing_plan_current"] is False
    assert updated["inputs"]["proposal_sections"][0]["text"]=="보존할 초안"
