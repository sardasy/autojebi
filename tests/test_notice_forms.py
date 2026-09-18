import copy
import hashlib
import io
import zipfile

import pytest
from fastapi import HTTPException
from lxml import etree
from sqlalchemy import update

from api.workspace import notice_forms as forms
from api.workspace import service
from api.workspace.tables import workspaces

XML = '''<?xml version="1.0" encoding="UTF-8"?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
 xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:kept="urn:keep">
<hp:p><hp:run><hp:t>본문 평가표(서식 2 참조)</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:t>&lt;서식 1&gt;</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:t>제안서</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:t>항목 1.</hp:t></hp:run></hp:p>
<hp:p paraPrIDRef="2"><hp:run charPrIDRef="80"><hp:t>...... (작성지침을 참고하여 자유롭게 기술)</hp:t></hp:run><hp:linesegarray/></hp:p>
<hp:p><hp:run><hp:t>&lt;서식 2&gt;</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:t>업체 일반현황 및 주요연혁</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:tbl rowCnt="3" colCnt="2" id="123">
<hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>상호명</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr rowAddr="0" colAddr="0"/></hp:tc>
<hp:tc><hp:subList><hp:p paraPrIDRef="1"><hp:run charPrIDRef="26"/><hp:linesegarray/></hp:p></hp:subList><hp:cellAddr rowAddr="0" colAddr="1"/><hp:cellSpan rowSpan="1" colSpan="1"/><hp:sz width="2000"/></hp:tc></hp:tr>
<hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>주민등록번호</hp:t></hp:run></hp:p></hp:subList></hp:tc>
<hp:tc><hp:subList><hp:p><hp:run charPrIDRef="26"/></hp:p></hp:subList></hp:tc></hp:tr>
<hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>법인( ), 개인( )</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr>
</hp:tbl></hp:run></hp:p></hs:sec>'''


def hwpx(xml=XML, extra=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("Contents/section0.xml", xml)
        archive.writestr("Contents/header.xml", '<head xmlns="urn:unchanged"/>')
        archive.writestr("Preview/PrvText.txt", "old preview")
        archive.writestr("Preview/PrvImage.png", b"old preview")
        archive.writestr("BinData/image.png", b"unchanged image")
        if extra:
            archive.writestr(*extra)
    return out.getvalue()


@pytest.fixture
def form_workspace(client, sqlite_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    response = client.post("/v2/notices", json={"notice_no": "FORM-TEST", "title": "원본 서식",
                           "source": "MANUAL_E2E", "raw": {"bidClseDt": "2027-01-20 10:00:00"}})
    assert response.status_code == 200
    state = client.post("/v2/notices/FORM-TEST/initialize").json()
    content = hwpx()
    path = tmp_path / "original.hwpx"
    path.write_bytes(content)
    doc = {"id": "form", "name": "제안요청서.hwpx", "role": "notice_source",
           "storage_path": str(path), "sha256": hashlib.sha256(content).hexdigest(), "text": "공고"}
    state["inputs"]["documents"] = [doc, {"id": "company", "name": "기존 작성자료",
        "role": "company_reference", "text": "미림씨스콘은 전력전자 유통 회사입니다.", "confirmed": False}]
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=state["inputs"]))
    return state, doc


def request_for(client, doc):
    found = client.get("/v2/notices/FORM-TEST/form-fields")
    assert found.status_code == 200, found.text
    fields = found.json()["documents"][0]["fields"]
    return {"version": 1, "document_id": "form", "source_sha256": doc["sha256"],
            "idempotency_key": "form-save", "note": "원본 위치에 참고자료 기반 초안 저장",
            "fields": [{"field_id": field["id"], "value": "첫째 줄\n둘째 줄" if field["kind"] == "paragraph" else "미림씨스콘",
                        "reference": {"document_id": "company", "quote": "미림씨스콘은 전력전자 유통 회사입니다."}}
                       for field in fields if field["kind"] != "choice"]}


def review_request(client, doc, complete=True):
    body = request_for(client, doc)
    if complete:
        fields = client.get("/v2/notices/FORM-TEST/form-fields").json()["documents"][0]["fields"]
        choice = next(f for f in fields if f["kind"] == "choice")
        body["fields"].append({"field_id": choice["id"], "value": "법인(●), 개인( )",
                               "reference": body["fields"][0]["reference"]})
    assert client.post("/v2/notices/FORM-TEST/form-fillings", json=body).status_code == 200
    target = client.get("/v2/notices/FORM-TEST/form-fillings/form/review").json()
    assert target["version"] == 2 and target["review_status"] == "pending"
    assert target["unfilled_count"] == (0 if complete else 1)
    return {"version": target["version"], "output_sha256": target["output_sha256"],
            "approved": True, "source_checked": True, "content_checked": True,
            "layout_checked": True, "note": "원본·근거·한글 배치 대조 완료"}


def test_form_review_records_exact_output_and_rejection_without_approving_evidence(client, form_workspace):
    _, doc = form_workspace
    body = review_request(client, doc)
    path = "/v2/notices/FORM-TEST/form-fillings/form"
    downloaded = client.get(path + "/download", params={"version": 2, "output_sha256": body["output_sha256"]})
    assert hashlib.sha256(downloaded.content).hexdigest() == body["output_sha256"]
    result = client.post(path + "/review", json=body)
    assert result.status_code == 200, result.text
    state = result.json()
    filling = state["inputs"]["form_fillings"][0]
    assert state["version"] == 3 and filling["review_status"] == "approved"
    assert filling["review"]["output_sha256"] == body["output_sha256"]
    assert filling["review"]["input_version"] == 3 and filling["review"]["note"] == body["note"]
    assert any(r["action"] == "notice_form_review" for r in state["reviews"])
    assert not any("원본 양식" in issue for issue in state["blockers"])
    assert not state["ready"] and state["decision"] == "pending"
    assert state["inputs"]["documents"][1]["role"] == "company_reference"
    assert not state["inputs"]["documents"][1]["confirmed"]
    assert client.get(path + "/download").content == downloaded.content
    assert client.get(path + "/download").headers["x-form-review"].startswith("approved;")
    assert client.post(path + "/review", json=body).status_code == 409
    assert client.get(path + "/download", params={"version": 2}).status_code == 409
    assert client.get(path + "/download", params={"output_sha256": "0" * 64}).status_code == 409
    rejected = client.post(path + "/review", json={**body, "version": 3, "approved": False}).json()
    assert rejected["inputs"]["form_fillings"][0]["review_status"] == "rejected"
    assert any("원본 양식" in issue for issue in rejected["blockers"])


@pytest.mark.parametrize("patch,code", [
    ({"layout_checked": False}, 422), ({"content_checked": False}, 422),
    ({"source_checked": False}, 422), ({"note": " "}, 422),
    ({"version": 1}, 409), ({"output_sha256": "0" * 64}, 409),
])
def test_form_approval_guards(client, form_workspace, patch, code):
    _, doc = form_workspace
    body = review_request(client, doc)
    response = client.post("/v2/notices/FORM-TEST/form-fillings/form/review", json={**body, **patch})
    assert response.status_code == code, response.text
    assert client.get("/v2/notices/FORM-TEST/workspace").json()["version"] == 2


def test_unfilled_form_can_be_rejected_but_not_approved(client, form_workspace):
    _, doc = form_workspace
    body = review_request(client, doc, complete=False)
    path = "/v2/notices/FORM-TEST/form-fillings/form/review"
    assert client.post(path, json=body).json()["detail"]["code"] == "form_unfilled"
    assert client.post(path, json={**body, "approved": False}).status_code == 200


@pytest.mark.parametrize("mutation", ["company", "reference", "value", "disk", "mapping"])
def test_form_review_becomes_invalid_when_inputs_or_files_change(client, form_workspace, sqlite_engine, mutation):
    _, doc = form_workspace
    body = review_request(client, doc)
    path = "/v2/notices/FORM-TEST/form-fillings/form/review"
    assert client.post(path, json=body).status_code == 200
    with sqlite_engine.begin() as conn:
        ws = service.load(conn, "FORM-TEST")
        changed = copy.deepcopy(ws["inputs"])
        if mutation == "company":
            changed["company"]["name"] = "변경 회사"
        elif mutation == "reference":
            changed["documents"][1]["text"] += " 변경"
        elif mutation == "value":
            changed["form_fillings"][0]["fields"][0]["value"] += " 변경"
        elif mutation == "mapping":
            changed["form_fillings"][0]["mapping_sha256"] = "0" * 64
        else:
            from pathlib import Path
            Path(doc["storage_path"]).write_bytes(b"changed file")
        if mutation != "disk":
            updated = service.change(conn, ws, changed, "test_change", "자료 변경")
            assert updated["inputs"]["form_fillings"][0]["review_status"] == "pending"
            assert updated["inputs"]["form_fillings"][0]["review"] == ws["inputs"]["form_fillings"][0]["review"]
    state = client.get("/v2/notices/FORM-TEST/workspace").json()
    assert not state["ready"] and any("원본 양식" in issue for issue in state["blockers"])
    assert client.post(path, json=body).status_code == 409


def test_actual_format_copy_preserves_geometry_and_exact_readback(client, form_workspace):
    state, doc = form_workspace
    body = request_for(client, doc)
    result = client.post("/v2/notices/FORM-TEST/form-fillings", json=body)
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved["version"] == 2 and not saved["ready"]
    assert saved["inputs"]["form_fillings"][0]["review_status"] == "pending"
    saved["inputs"]["documents"][0] = doc  # public responses intentionally omit storage_path
    content, filename, report = forms.export_filling(saved["inputs"], "form")
    assert filename.endswith("_작성사본_검토필요.hwpx")
    assert report["readback_verified"] and not report["layout_verified"]
    assert report["field_count"] == 3 and report["filled_count"] == 2
    original_bytes = forms._source(doc)
    assert hashlib.sha256(original_bytes).hexdigest() == doc["sha256"]
    with zipfile.ZipFile(io.BytesIO(content)) as after, zipfile.ZipFile(io.BytesIO(original_bytes)) as before:
        assert before.namelist() == after.namelist()
        assert after.infolist()[0].compress_type == zipfile.ZIP_STORED
        for name in ("mimetype", "Contents/header.xml", "BinData/image.png"):
            assert before.read(name) == after.read(name)
        assert before.read("Preview/PrvImage.png") != after.read("Preview/PrvImage.png")
        root = etree.fromstring(after.read("Contents/section0.xml"))
        original = etree.fromstring(before.read("Contents/section0.xml"))
        assert root.nsmap == original.nsmap
        for tag in ("tbl", "cellAddr", "cellSpan", "sz"):
            assert [n.attrib for n in root.findall(f".//hp:{tag}", forms.NS)] == [
                n.attrib for n in original.findall(f".//hp:{tag}", forms.NS)]
        assert "미림씨스콘" in forms._readback(root)
        assert "법인( ), 개인( ) [확인 필요]" in forms._readback(root)
        assert len(root.findall(".//hp:lineBreak", forms.NS)) == 1
    download = client.get("/v2/notices/FORM-TEST/form-fillings/form/download")
    assert download.status_code == 200
    assert "layout-review-required" in download.headers["x-form-review"]
    assert "filename*=UTF-8''" in download.headers["content-disposition"]


def test_references_versions_and_idempotency(client, form_workspace):
    _, doc = form_workspace
    body = request_for(client, doc)
    wrong = copy.deepcopy(body)
    wrong["fields"][0]["reference"]["quote"] = "없는 발췌문"
    assert client.post("/v2/notices/FORM-TEST/form-fillings", json=wrong).status_code == 422
    wrong = copy.deepcopy(body)
    del wrong["fields"][0]["reference"]
    assert client.post("/v2/notices/FORM-TEST/form-fillings", json=wrong).status_code == 422
    wrong = {**body, "source_sha256": "a" * 64}
    assert client.post("/v2/notices/FORM-TEST/form-fillings", json=wrong).status_code == 409
    saved = client.post("/v2/notices/FORM-TEST/form-fillings", json=body)
    assert saved.status_code == 200, saved.text
    assert client.post("/v2/notices/FORM-TEST/form-fillings", json=body).json()["version"] == 2
    assert client.post("/v2/notices/FORM-TEST/form-fillings", json={**body, "note": "다른 내용"}).status_code == 409
    assert client.post("/v2/notices/FORM-TEST/form-fillings", json={**body, "idempotency_key": "new"}).status_code == 409


@pytest.mark.parametrize("mutation", ["source", "mapping", "reference", "quote"])
def test_export_rejects_changed_source_mapping_or_reference(client, form_workspace, mutation):
    _, doc = form_workspace
    result = client.post("/v2/notices/FORM-TEST/form-fillings", json=request_for(client, doc))
    assert result.status_code == 200
    inputs = result.json()["inputs"]
    inputs["documents"][0] = copy.deepcopy(doc)
    if mutation == "source":
        inputs["documents"][0]["sha256"] = "b" * 64
    elif mutation == "mapping":
        inputs["form_fillings"][0]["fields"][0]["mapping"]["location"] = "Contents/section0.xml|/anything"
    elif mutation == "reference":
        inputs["documents"][1]["text"] += " 변경됨"
    else:
        inputs["form_fillings"][0]["fields"][0]["reference"]["quote"] = "없는 인용"
    with pytest.raises(HTTPException):
        forms.export_filling(inputs, "form")


@pytest.mark.parametrize("content", [
    hwpx(extra=("../escape.txt", "bad")),
    hwpx(extra=("Contents/SECTION0.xml", "duplicate")),
    hwpx(XML.replace("<hs:sec", '<!DOCTYPE root [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><hs:sec', 1)),
    hwpx("<broken>"), b"not a zip",
])
def test_unsafe_archives_are_explicitly_unsupported(client, form_workspace, tmp_path, content):
    _, doc = form_workspace
    path = tmp_path / "unsafe.hwpx"
    path.write_bytes(content)
    inspected = forms.inspect_document({**doc, "storage_path": str(path),
                                        "sha256": hashlib.sha256(content).hexdigest()})
    assert not inspected["supported"] and inspected["reason"]


def test_no_marker_hwp_pdf_protected_slots_and_bad_choice(client, form_workspace):
    _, doc = form_workspace
    inventory = client.get("/v2/notices/FORM-TEST/form-fields").json()
    fields = inventory["documents"][0]["fields"]
    assert not any("주민" in f["label"] for f in fields)
    assert not forms.inspect_document({**doc, "name": "original.hwp"})["supported"]
    assert not forms.inspect_document({**doc, "name": "original.pdf"})["supported"]
    archive, roots = forms._archive(hwpx(XML.replace("&lt;서식 1&gt;", "서식 1 참고").replace("&lt;서식 2&gt;", "서식 2 참고")))
    with archive:
        assert forms._fields(roots, doc["sha256"]) == []
    choice = next(f for f in fields if f["kind"] == "choice")
    body = request_for(client, doc)
    body["fields"] = [{"field_id": choice["id"], "value": "법인입니다",
                       "web_reference": {"title": "노션 참고", "url": "https://www.notion.so/example", "quote": "법인 참고"}}]
    assert client.post("/v2/notices/FORM-TEST/form-fillings", json=body).status_code == 422
    body["fields"][0]["value"] = "법인(●), 개인( )"
    result = client.post("/v2/notices/FORM-TEST/form-fillings", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["inputs"]["form_fillings"][0]["fields"][0]["web_reference"]["verified"] is False


def cost_xml(title="산출내역서"):
    rows = [["품 명", "수량", "단 가", "금 액"], ["시험 장치", "2", "", ""],
            ["", "", "공급가액", ""], ["", "", "부가가치세", ""], ["", "", "합 계", ""]]
    body = []
    for ri, row in enumerate(rows):
        cells = []
        for ci, value in enumerate(row):
            cells.append(f'<hp:tc><hp:subList><hp:p paraPrIDRef="1"><hp:run charPrIDRef="2">'
                         f'<hp:t>{value}</hp:t></hp:run></hp:p></hp:subList>'
                         f'<hp:cellAddr rowAddr="{ri}" colAddr="{ci}"/>'
                         '<hp:cellSpan rowSpan="1" colSpan="1"/></hp:tc>')
        body.append("<hp:tr>" + "".join(cells) + "</hp:tr>")
    return (f'<hs:sec xmlns:hs="urn:section" xmlns:hp="{forms.HP}">'
            f'<hp:p><hp:run><hp:t>{title}</hp:t></hp:run></hp:p>'
            '<hp:p><hp:run><hp:tbl rowCnt="5" colCnt="4">' + "".join(body)
            + '</hp:tbl></hp:run></hp:p></hs:sec>')


def test_cost_sheet_only_exposes_prices_preserves_quantity_and_never_calculates(
    client, form_workspace, sqlite_engine, tmp_path,
):
    state, doc = form_workspace
    content = hwpx(cost_xml())
    path = tmp_path / "cost.hwpx"
    path.write_bytes(content)
    doc = {**doc, "name": "산출 공내역서.hwpx", "storage_path": str(path),
           "sha256": hashlib.sha256(content).hexdigest()}
    state["inputs"]["documents"][0] = doc
    state["inputs"]["documents"][1]["text"] = "시험 장치 단가 10,000원"
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=state["inputs"]))
    catalog = client.get("/v2/notices/FORM-TEST/form-fields").json()
    fields = catalog["documents"][0]["fields"]
    assert len(fields) == 5 and all(f["kind"] == "amount" for f in fields)
    assert not any(f["label"] == "수량" for f in fields)
    body = {"version": 1, "document_id": "form", "source_sha256": doc["sha256"],
            "idempotency_key": "quote", "note": "실제 견적 확인 후 입력",
            "fields": [{"field_id": fields[0]["id"], "value": "10,000",
                        "reference": {"document_id": "company", "quote": "시험 장치 단가 10,000원"}}]}
    wrong = copy.deepcopy(body)
    wrong["fields"][0]["value"] = "예상금액 임의계산"
    assert client.post("/v2/notices/FORM-TEST/form-fillings", json=wrong).status_code == 422
    saved = client.post("/v2/notices/FORM-TEST/form-fillings", json=body)
    assert saved.status_code == 200, saved.text
    inputs = saved.json()["inputs"]
    inputs["documents"][0] = doc
    data, _, report = forms.export_filling(inputs, "form")
    assert report["filled_count"] == 1 and report["unfilled_count"] == 4
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("Contents/section0.xml"))
        assert "10,000" in forms._readback(root)
        rows = root.findall(".//hp:tbl/hp:tr", forms.NS)
        cells = rows[1].findall("hp:tc", forms.NS)
        assert forms._readback(cells[0]) == "시험 장치"
        assert forms._readback(cells[1]) == "2"
        assert forms._readback(cells[3]) == "[확인 필요]"  # not inferred as 20,000
    archive, roots = forms._archive(hwpx(cost_xml("장비 사양서")))
    with archive:
        assert forms._fields(roots, doc["sha256"]) == []
