"""Packaging an actual attached form must preserve its sources and review boundaries."""

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from sqlalchemy import select, update

from api.workspace import service
from api.workspace.execution import run_package
from api.workspace.tables import reviews, workspaces

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
XML = f"""<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="{HP}">
<hp:p><hp:run><hp:t>&lt;서식 2&gt;</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:t>업체 일반현황</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:tbl id="table-1" rowCnt="1" colCnt="2">
<hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>상호명</hp:t></hp:run></hp:p></hp:subList>
<hp:cellAddr rowAddr="0" colAddr="0"/></hp:tc>
<hp:tc><hp:subList><hp:p paraPrIDRef="1"><hp:run charPrIDRef="26"/></hp:p></hp:subList>
<hp:cellAddr rowAddr="0" colAddr="1"/><hp:cellSpan rowSpan="1" colSpan="1"/>
<hp:cellSz width="3000" height="1000"/></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
</hs:sec>"""


@pytest.fixture
def saved_form_package(client, sqlite_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    notice_no = "FORM-PACKAGE-TEST"
    response = client.post(
        "/v2/notices",
        json={
            "notice_no": notice_no,
            "title": "첨부 양식 패키지 검증",
            "source": "MANUAL_E2E",
            "raw": {"bidClseDt": "2027-01-20 10:00:00"},
        },
    )
    assert response.status_code == 200
    initial = client.post(f"/v2/notices/{notice_no}/initialize").json()
    original = io.BytesIO()
    with zipfile.ZipFile(original, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("Contents/section0.xml", XML)
        archive.writestr("Contents/header.xml", '<header><style id="26"/></header>')
        archive.writestr("BinData/logo.png", b"preserved-original-image")
        archive.writestr("Preview/PrvText.txt", "original preview")
    source = tmp_path / "original.hwpx"
    source.write_bytes(original.getvalue())
    reference = tmp_path / "company-reference.txt"
    reference_text = "작성 예시 회사명은 샘플 주식회사입니다. 실제 자격증빙이 아닙니다."
    reference.write_text(reference_text, encoding="utf-8")
    documents = [
        {
            "id": "original",
            "name": "제안요청서.hwpx",
            "role": "notice_source",
            "storage_path": str(source),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "text": "서식 2 업체 일반현황 상호명",
            "confirmed": False,
        },
        {
            "id": "reference",
            "name": "회사 참고자료.txt",
            "role": "company_reference",
            "storage_path": str(reference),
            "sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "text": reference_text,
            "confirmed": False,
        },
    ]
    inputs = initial["inputs"]
    inputs["documents"] = documents
    inputs["checklist"] = [{"id": "manufacturer", "name": "컴퓨터서버 직접생산확인증명서"}]
    with sqlite_engine.begin() as conn:
        conn.execute(
            update(workspaces).where(workspaces.c.notice_no == notice_no).values(inputs=inputs)
        )
    inventory = client.get(f"/v2/notices/{notice_no}/form-fields").json()
    field = inventory["documents"][0]["fields"][0]
    saved = client.post(
        f"/v2/notices/{notice_no}/form-fillings",
        json={
            "version": initial["version"],
            "document_id": "original",
            "source_sha256": documents[0]["sha256"],
            "idempotency_key": "package-form-fill",
            "note": "참고자료 기반 원본 서식 초안",
            "fields": [
                {
                    "field_id": field["id"],
                    "value": "샘플 주식회사",
                    "reference": {"document_id": "reference", "quote": reference_text},
                }
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["ready"] is False
    with sqlite_engine.connect() as conn:
        state = service.load(conn, notice_no)
    return state, source, reference


def test_package_includes_verified_original_form_without_mutating_sources_or_approval(
    client, sqlite_engine, tmp_path, saved_form_package
):
    state, source, reference = saved_form_package
    before = copy.deepcopy(state["inputs"])
    source_bytes, reference_bytes = source.read_bytes(), reference.read_bytes()
    with sqlite_engine.connect() as conn:
        reviews_before = [
            dict(row)
            for row in conn.execute(
                select(reviews).where(reviews.c.notice_no == state["notice_no"])
            ).mappings()
        ]
    folder = tmp_path / "package-output"
    folder.mkdir()
    job = {
        "notice_no": state["notice_no"],
        "input_version": state["version"],
        "snapshot": state["inputs"],
    }
    result = run_package(sqlite_engine, job, folder)
    package_path = Path(result["artifact"])
    assert hashlib.sha256(package_path.read_bytes()).hexdigest() == result["sha256"]

    with zipfile.ZipFile(package_path) as package:
        manifest_bytes = package.read("manifest.json")
        manifest = json.loads(manifest_bytes)
        entries = [item for item in manifest["files"] if item.get("name", "").startswith("forms/")]
        assert len(entries) == 1
        entry = entries[0]
        filled_bytes = package.read(entry["name"])
        assert entry["name"].endswith(".hwpx")
        assert hashlib.sha256(filled_bytes).hexdigest() == entry["sha256"]
        report = entry["original_form"]
        assert report["output_sha256"] == entry["sha256"]
        assert report["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
        assert report["field_count"] == report["filled_count"] == 1
        assert report["unfilled_count"] == 0
        assert report["readback_verified"] is True
        assert report["layout_verified"] is False
        assert report["review_status"] == "pending"
        with zipfile.ZipFile(io.BytesIO(filled_bytes)) as form:
            root = etree.fromstring(form.read("Contents/section0.xml"))
            texts = "".join(root.itertext())
            assert "샘플 주식회사" in texts and "상호명" in texts
            assert form.read("BinData/logo.png") == b"preserved-original-image"
        for doc in before["documents"]:
            source_entry = next(
                item
                for item in manifest["files"]
                if item.get("name", "").startswith(f"sources/{doc['id']}.")
            )
            contents = package.read(source_entry["name"])
            assert hashlib.sha256(contents).hexdigest() == source_entry["sha256"] == doc["sha256"]
        portable = manifest["inputs"]
        assert all("storage_path" not in doc for doc in portable["documents"])
        assert str(source) not in manifest_bytes.decode("utf-8")
        assert str(reference) not in manifest_bytes.decode("utf-8")
        company = next(doc for doc in portable["documents"] if doc["id"] == "reference")
        assert company["role"] == "company_reference" and company["confirmed"] is False
        assert portable["form_fillings"][0]["review_status"] == "pending"
        assert all(review["action"] not in {"approved", "ready"} for review in manifest["reviews"])
        assert "컴퓨터서버 직접생산확인증명서" in package.read("missing.txt").decode("utf-8")
        assert all("details" not in review for review in manifest["reviews"])

    # Sanitizing an exported manifest must never strip paths from the job or persisted inputs.
    assert job["snapshot"] == before
    assert source.read_bytes() == source_bytes
    assert reference.read_bytes() == reference_bytes
    with sqlite_engine.connect() as conn:
        persisted = service.load(conn, state["notice_no"])
        reviews_after = [
            dict(row)
            for row in conn.execute(
                select(reviews).where(reviews.c.notice_no == state["notice_no"])
            ).mappings()
        ]
    assert persisted["inputs"] == before
    assert reviews_after == reviews_before
    assert persisted["decision"] == state["decision"]
    response = client.get(f"/v2/notices/{state['notice_no']}/workspace")
    assert response.status_code == 200 and response.json()["ready"] is False
