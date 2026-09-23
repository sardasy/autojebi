"""ADR 0002 fitness functions: exact citations, approval anchors and ZIP revisions."""

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest
from sqlalchemy import update

from api.parsing.attachment_text import extract_hwpx, extract_zip
from api.workspace import notice_brief, service
from api.workspace.executors.extract import extract
from api.workspace.executors.package import run_package
from api.workspace.forms import filling
from api.workspace.tables import workspaces
from tests.test_notice_forms import XML, hwpx
from tests.test_notice_forms import form_workspace as _form_workspace

form_workspace = _form_workspace


def zipped(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return stream.getvalue()


def source(text="", **extra):
    return {"id": "source", "role": "notice_source", "name": "공고.hwpx", "text": text,
            "sha256": "a" * 64, "extraction": {"complete": True}, **extra}


def test_existing_hwpx_enrichment_preserves_canonical_text(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    raw = hwpx()
    path = tmp_path / "source.hwpx"
    path.write_bytes(raw)
    canonical = extract_hwpx(raw)["text"]
    doc = source(canonical, storage_path=str(path), sha256=hashlib.sha256(raw).hexdigest(), text_origin="hwpx")
    doc["extraction"]["text_rule_version"] = 2
    enriched = extract({"snapshot": {"documents": [doc]}})["documents"][0]
    assert enriched["text"] == canonical
    assert enriched["extraction"]["presentation"]["spans"]
    doc["text"] = "보존해야 하는 기존 본문"
    mismatch = extract({"snapshot": {"documents": [doc]}})["documents"][0]
    assert mismatch["text"] == doc["text"]
    assert mismatch["extraction"]["presentation"]["status"] == "partial"


def test_hwpx_canonical_text_and_nested_archive_offsets_stay_exact():
    raw = hwpx(extra=("Contents/section1.xml", XML.replace("제안서", "😀제안서")))
    result = extract_hwpx(raw)
    expected = "\n".join(" ".join(ElementTree.fromstring(xml).itertext())
                         for xml in (XML, XML.replace("제안서", "😀제안서")))
    assert result["text"] == expected
    nested = extract_zip(zipped([("folder/nested.zip", zipped([("안내.hwpx", raw)]))]))
    assert nested["text"] == f"[ZIP 파일 folder/nested.zip]\n[ZIP 파일 안내.hwpx]\n{expected}"
    spans = nested["extraction"]["presentation"]["spans"]
    assert spans and nested["extraction"]["presentation"]["status"] == "complete"
    assert all(s["member_path"] == ["folder/nested.zip", "안내.hwpx"] for s in spans)
    assert any(nested["text"][s["start"]:s["end"]] == "😀제안서" for s in spans)
    assert all(0 <= s["start"] < s["end"] <= len(nested["text"]) for s in spans)


@pytest.mark.parametrize("label", ["사업 예산", "사업예산", "총 사업비", "구축 예산", "예산금액"])
@pytest.mark.parametrize("separator", [": ", "\r\n", " "])
def test_budget_variants_keep_tax_condition_and_exact_quote(label, separator):
    text = f"{label}{separator}총 260,000,000원 (부가세 별도)"
    brief = notice_brief.build({"documents": [source(text)]})
    items = next(g["items"] for g in brief["points"] if g["label"] == "예산")
    assert len(items) == 1
    assert "부가세 별도" in items[0]["quote"]
    for item in items:
        assert text[item["start"]:item["end"]] == item["quote"]


@pytest.mark.parametrize("label", ["납품기한", "납품 설치 기한", "계약기간"])
def test_period_and_evaluation_variants(label):
    text = f"1) {label}: 계약일로부터 120일 이내\n평가점수의 종합점수가 85.5점 이상인 자를 적격자로 선정한다. 허위 서류는 제외한다."
    brief = notice_brief.build({"documents": [source(text)]})
    points = {g["label"]: g["items"] for g in brief["points"]}
    assert "120일" in points["계약·수행 기간"][0]["quote"]
    assert "85.5점" in points["평가 기준"][0]["quote"]
    assert "허위 서류는 제외한다" in points["평가 기준"][0]["quote"]


def test_failure_is_not_absence_and_found_items_keep_global_warning():
    doc = source("사업 예산: 100원", extraction={"complete": False})
    brief = notice_brief.build({"documents": [doc]})
    assert brief["warnings"]
    assert {p["label"]: p["state"] for p in brief["points"]}["예산"] == "found"
    assert all(p["state"] != "absent_confirmed" for p in brief["points"])
    absent = notice_brief.build({"documents": [source("일반 만족도는 85점 이상입니다.", name="사업예산.pdf")]})
    assert all(p["state"] == "not_detected" for p in absent["points"])


def test_only_equal_complete_content_groups_never_stems_or_partial_text():
    first = source("사업예산: 100원", id="a", name="공고.pdf")
    second = source("사업예산: 200원", id="b", name="공고.hwpx")
    assert notice_brief.groups({"documents": [first, second]}) == [["a"], ["b"]]
    second["text"] = "사업예산:\n100원"
    assert notice_brief.groups({"documents": [first, second]}) == [["a", "b"]]
    second["extraction"]["complete"] = False
    assert notice_brief.groups({"documents": [first, second]}) == [["a"], ["b"]]


def test_display_metadata_preserves_basis_but_failures_and_body_changes_do_not():
    inputs = {"documents": [source("사업예산: 100원")]}
    previous = filling.review_basis(inputs)
    changed = copy.deepcopy(inputs)
    changed["documents"][0]["extraction"]["presentation"] = {"version": 1, "spans": []}
    assert filling.review_basis(changed) == previous
    changed["documents"][0]["extraction"]["complete"] = False
    assert filling.review_basis(changed) != previous


def test_title_after_form_number_keeps_issued_certificates_protected():
    raw = hwpx(XML.replace("&lt;서식 1&gt;", "[서식 1] 제안서")
               .replace("&lt;서식 2&gt;", "[서식 2] 업체 일반현황"))
    archive, roots = filling._archive(raw)
    with archive:
        fields = filling._fields(roots, hashlib.sha256(raw).hexdigest())
    assert any(f["label"] == "상호명" for f in fields)
    assert not any("주민" in f["label"] for f in fields)
    certificate = hwpx(XML.replace("&lt;서식 2&gt;", "[서식 2] 실적증명서"))
    archive, roots = filling._archive(certificate)
    with archive:
        fields = filling._fields(roots, hashlib.sha256(certificate).hexdigest())
    assert not any(f["label"] == "상호명" for f in fields)


def test_snapshot_changes_only_when_displayed_items_change():
    inputs = {"documents": [source("사업예산: 100원")], "source_reviewed": True}
    baseline = notice_brief.review_snapshot(inputs)
    history = [{"action": "source_review", "details": {"brief_snapshot": baseline}}]
    assert notice_brief.public_brief(inputs, history)["review_comparison"] == "unchanged"
    inputs["documents"][0]["text"] = "사업예산: 200원"
    assert notice_brief.public_brief(inputs, history)["review_comparison"] == "updated"
    assert notice_brief.public_brief(inputs, [{"action": "source_review", "details": {}}])["review_comparison"] == "unavailable"


def test_zip_form_save_readback_revision_and_original_retained(client, sqlite_engine, form_workspace, tmp_path):
    ws, doc = form_workspace
    raw = zipped([("one/양식.hwpx", hwpx()), ("two/양식.hwpx", hwpx()), ("직접작성.hwp", b"binary")])
    path = tmp_path / "notice.zip"
    path.write_bytes(raw)
    doc.update(name="자료.zip", storage_path=str(path), sha256=hashlib.sha256(raw).hexdigest())
    ws["inputs"]["documents"][0] = doc
    reference = ws["inputs"]["documents"][1]
    reference_path = tmp_path / "company-reference.txt"
    reference_path.write_text(reference["text"], encoding="utf-8")
    reference.update(storage_path=str(reference_path), sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest())
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=ws["inputs"]))
    prefix = "/v2/notices/FORM-TEST"
    catalog = client.get(f"{prefix}/form-fields").json()
    targets = [d for d in catalog["documents"] if d["supported"]]
    assert len(targets) == 2 and targets[0]["document_id"] != targets[1]["document_id"]
    assert any("수동 작성" in d.get("reason", "") for d in catalog["documents"])
    target = targets[0]
    field = next(f for f in target["fields"] if f["kind"] == "paragraph")
    body = {"version": ws["version"], "document_id": target["document_id"],
            "source_sha256": target["sha256"], "idempotency_key": "zip-test", "note": "TEST ONLY",
            "fields": [{"field_id": field["id"], "value": "미림씨스콘",
                        "reference": {"document_id": "company", "quote": "미림씨스콘은 전력전자 유통 회사입니다."}}]}
    saved = client.post(f"{prefix}/form-fillings", json=body)
    assert saved.status_code == 200, saved.text
    assert len(saved.json()["inputs"]["documents"]) == 2
    filled = saved.json()["inputs"]["form_fillings"][0]
    assert filled["container_sha256"] == doc["sha256"] and filled["member_path"] == ["one/양식.hwpx"]
    url = f"{prefix}/form-fillings/{target['document_id']}/download"
    output = client.get(url)
    assert output.status_code == 200
    with zipfile.ZipFile(io.BytesIO(output.content)) as archive:
        assert "미림씨스콘" in archive.read("Contents/section0.xml").decode()
        assert archive.read("BinData/image.png") == b"unchanged image"
    assert path.read_bytes() == raw
    with sqlite_engine.connect() as conn:
        current = service.load(conn, "FORM-TEST")
    folder = tmp_path / "package"
    folder.mkdir()
    package = run_package(sqlite_engine, {"notice_no": "FORM-TEST", "input_version": current["version"],
                                          "snapshot": current["inputs"]}, folder)
    with zipfile.ZipFile(Path(package["artifact"])) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        entry = next(f for f in manifest["files"] if f.get("name", "").startswith("forms/"))
        assert archive.read(entry["name"]) == output.content
        assert entry["original_form"]["container_sha256"] == doc["sha256"]
        assert entry["original_form"]["member_path"] == ["one/양식.hwpx"]
    raw2 = zipped([("one/양식.hwpx", hwpx()), ("정정.txt", b"revision")])
    replacement = tmp_path / "revision.zip"
    replacement.write_bytes(raw2)
    with sqlite_engine.begin() as conn:
        current = service.load(conn, "FORM-TEST")
        inputs = copy.deepcopy(current["inputs"])
        inputs["documents"][0].update(storage_path=str(replacement), sha256=hashlib.sha256(raw2).hexdigest())
        service.change(conn, current, inputs, "extract_result", "정정 ZIP 검증")
    fresh = client.get(f"{prefix}/form-fields").json()
    assert target["document_id"] not in [t["document_id"] for t in fresh["documents"]]
    assert fresh["fillings"] == []
    assert fresh["retired_fillings"][0]["document_id"] == target["document_id"]
    assert client.get(url).status_code == 409
    assert client.post(f"{prefix}/form-fillings", json={**body, "version": fresh["version"], "idempotency_key": "new"}).status_code == 409


def test_human_absence_invalidated_by_added_source(client, sqlite_engine, form_workspace):
    ws, _ = form_workspace
    prefix = "/v2/notices/FORM-TEST"
    brief = client.get(f"{prefix}/workspace").json()["notice_brief"]
    body = {"version": ws["version"], "kind": "absent", "label": "예산", "document_ids": ["form"],
            "source_signature": brief["source_signature"], "original_checked": True, "note": "합성 원본 전체 대조"}
    saved = client.post(f"{prefix}/source-display-reviews", json=body)
    assert saved.status_code == 200, saved.text
    assert next(p for p in saved.json()["notice_brief"]["points"] if p["label"] == "예산")["state"] == "absent_confirmed"
    with sqlite_engine.begin() as conn:
        current = service.load(conn, "FORM-TEST")
        inputs = copy.deepcopy(current["inputs"])
        inputs["documents"].append(source("추가 공고", id="extra"))
        service.change(conn, current, inputs, "extract_result", "추가 원본")
    brief = client.get(f"{prefix}/workspace").json()["notice_brief"]
    assert all(p["state"] != "absent_confirmed" for p in brief["points"])


def test_link_candidate_requires_matching_location_and_never_auto_resolves(client, sqlite_engine, form_workspace):
    ws, doc = form_workspace
    doc["text"] = "제안요청서 및 평가표 확인. 평가기준: 기술평가 85점 이상 협상 대상 선정"
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=ws["inputs"]))
    prefix = "/v2/notices/FORM-TEST"
    result = client.get(f"{prefix}/workspace").json()
    need = next(n for n in result["source_needs"] if n["name"] == "평가표")
    assert need["state"] == "missing"
    candidate = need["candidates"][0]
    assert candidate["quote"] in doc["text"]
    item = {"id": need["id"], "state": "linked", "document_id": doc["id"],
            "resolution_quote": candidate["quote"], "locator": "wrong", "note": "TEST ONLY 합성 후보 대조"}
    assert client.put(f"{prefix}/source-needs", json={"version": ws["version"], "items": [item]}).status_code == 409
    item["locator"] = candidate["locator"]
    saved = client.put(f"{prefix}/source-needs", json={"version": ws["version"], "items": [item]})
    assert saved.status_code == 200, saved.text
    assert next(n for n in saved.json()["source_needs"] if n["id"] == need["id"])["state"] == "linked"
    assert saved.json()["ready"] is False
