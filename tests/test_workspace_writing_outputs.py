"""Written submission items need the matching approved original form."""

import copy
import hashlib
import io
import zipfile

import pytest
from sqlalchemy import update

from api.workspace import service
from api.workspace.forms import filling as notice_forms
from api.workspace.output_plan import writing_output_issues
from api.workspace.tables import workspaces

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
PREFIX = "/v2/notices/WRITING-OUTPUTS"


@pytest.fixture
def written_forms(client, sqlite_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    response = client.post("/v2/notices", json={"notice_no": "WRITING-OUTPUTS",
                           "title": "원본 서식 대응 검증", "source": "MANUAL_E2E"})
    assert response.status_code == 200
    state = client.post(PREFIX + "/initialize").json()
    titles = ["업체 일반현황", "수행 실적"]
    paragraphs = []
    for index, heading in enumerate(titles, 1):
        paragraphs.append(f"""
<hp:p><hp:run><hp:t>&lt;서식 {index}&gt;</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:t>{heading}</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:tbl><hp:tr>
<hp:tc><hp:subList><hp:p><hp:run><hp:t>상호명</hp:t></hp:run></hp:p></hp:subList></hp:tc>
<hp:tc><hp:subList><hp:p><hp:run/></hp:p></hp:subList></hp:tc>
</hp:tr></hp:tbl></hp:run></hp:p>""")
    original = io.BytesIO()
    with zipfile.ZipFile(original, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("Contents/section0.xml", f'<hs:sec xmlns:hs="urn:section" xmlns:hp="{HP}">'
                         + "".join(paragraphs) + "</hs:sec>")
    path = tmp_path / "forms.hwpx"
    path.write_bytes(original.getvalue())
    source = {"id": "original", "name": "양식.hwpx", "role": "notice_source", "confirmed": False,
              "storage_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "text": "업체 일반현황 수행 실적 작성 후 제출", "text_origin": "extracted"}
    inputs = state["inputs"]
    inputs["documents"] = [source, {"id": "reference", "name": "참고자료", "role": "company_reference",
                                   "text": "시험 회사", "confirmed": False}]
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).where(workspaces.c.notice_no == "WRITING-OUTPUTS").values(inputs=inputs))
    plan = [{"id": f"target-{index}", "title": heading, "document_kind": "other_document",
             "action": "write", "document_id": "original", "quote": source["text"]}
            for index, heading in enumerate(titles)]
    result = client.put(PREFIX + "/writing-plan", json={"version": state["version"], "items": plan,
                                                       "note": "원본 서식의 제목 대조"})
    assert result.status_code == 200, result.text
    state = result.json()
    catalog = client.get(PREFIX + "/form-fields").json()
    fields = catalog["documents"][0]["fields"]
    assert len(fields) == 2
    result = client.post(PREFIX + "/form-fillings", json={"version": state["version"],
        "document_id": "original", "source_sha256": source["sha256"], "idempotency_key": "fill-both",
        "fields": [{"field_id": field["id"], "value": "시험 회사",
                    "reference": {"document_id": "reference", "quote": "시험 회사"}} for field in fields],
        "note": "테스트 서식 두 개 작성"})
    assert result.status_code == 200, result.text
    return path


def load_inputs(sqlite_engine):
    with sqlite_engine.connect() as conn:
        return service.load(conn, "WRITING-OUTPUTS")["inputs"]


def approve(client):
    target = client.get(PREFIX + "/form-fillings/original/review").json()
    result = client.post(PREFIX + "/form-fillings/original/review", json={
        "version": target["version"], "output_sha256": target["output_sha256"], "approved": True,
        "source_checked": True, "content_checked": True, "layout_checked": True,
        "note": "합성 서식 전체 내용과 배치 대조"})
    assert result.status_code == 200, result.text


def test_complete_original_form_approval_covers_each_matching_target_and_rejection_revokes(
    client, sqlite_engine, written_forms,
):
    assert len(writing_output_issues(load_inputs(sqlite_engine))) == 2
    approve(client)
    inputs = load_inputs(sqlite_engine)
    assert writing_output_issues(inputs) == []
    assert inputs["documents"][1]["role"] == "company_reference"
    assert inputs["documents"][1]["confirmed"] is False
    target = client.get(PREFIX + "/form-fillings/original/review").json()
    rejected = client.post(PREFIX + "/form-fillings/original/review", json={
        "version": target["version"], "output_sha256": target["output_sha256"], "approved": False,
        "note": "배치 재검토 필요"})
    assert rejected.status_code == 200
    assert len(writing_output_issues(load_inputs(sqlite_engine))) == 2


@pytest.mark.parametrize("patch", [
    {"title": "가격입찰서"}, {"title": "일반현황"}, {"document_id": "another-source"},
])
def test_same_document_or_similar_title_cannot_approve_an_unmatched_target(
    client, sqlite_engine, written_forms, patch,
):
    approve(client)
    inputs = copy.deepcopy(load_inputs(sqlite_engine))
    inputs["writing_plan"]["items"][0].update(patch)
    # Keep approval current to isolate the form-to-target matching rule.
    inputs["form_fillings"][0]["review"]["basis_sha256"] = notice_forms.review_basis(inputs)
    assert writing_output_issues(inputs) == [
        f"제출 양식 작성·검토 필요: {inputs['writing_plan']['items'][0]['title']}"
    ]


def test_changed_reference_and_changed_original_invalidate_matched_outputs(
    client, sqlite_engine, written_forms,
):
    approve(client)
    inputs = load_inputs(sqlite_engine)
    changed = copy.deepcopy(inputs)
    changed["documents"][1]["text"] = "시험 회사 참고자료 변경"
    assert len(writing_output_issues(changed)) == 2
    written_forms.write_bytes(b"changed original file")
    assert len(writing_output_issues(inputs)) == 2


def test_only_direct_non_proposal_writing_requires_a_matching_original_form():
    inputs = {"writing_plan": {"items": [
        {"id": "proposal", "title": "정성제안서", "action": "write", "document_kind": "qualitative_proposal"},
        {"id": "issued", "title": "사업자등록증", "action": "attach", "document_kind": "other_document"},
        {"id": "price", "title": "가격입찰서", "action": "electronic", "document_kind": "bid_document"},
    ]}}
    assert writing_output_issues(inputs) == []
    inputs["writing_plan"]["items"][-1]["action"] = "write"
    assert writing_output_issues(inputs) == ["제출 양식 작성·검토 필요: 가격입찰서"]
