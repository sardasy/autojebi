import ast
import copy
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from sqlalchemy import select, update

from api.parsing.attachment_text import extract_hwpx, extract_zip
from api.parsing.document_comparison import compare_document
from api.parsing.text_diff import Budget, diff_text
from api.workspace import document_jobs
from api.workspace.models import JobRequest
from api.workspace.tables import jobs, workspaces
from api.workspace.worker import run_once
from tests.document_comparison_samples import CONTROL, archive, reference, sample, section, table


def test_only_parameters_are_excluded_and_v1_stays_exact():
    xml = section(f'<hp:p><hp:run>{CONTROL}<hp:t>😀 Clickhere 9</hp:t></hp:run></hp:p>'
                  '<hp:p><hp:run><hp:t>표시 문자열</hp:t><hp:ctrl><hp:fieldEnd/></hp:ctrl></hp:run></hp:p>')
    raw = archive([("Contents/section0.xml", xml)])
    old, new = extract_hwpx(raw, rule_version=1), extract_hwpx(raw, rule_version=2)
    assert old["text"] == " ".join(ET.fromstring(xml).itertext())
    assert new["text"] == "😀 Clickhere 9 표시 문자열"
    assert len(new["extraction"]["excluded_controls"]) == 1
    assert new["extraction"]["offset_unit"] == "unicode_codepoint"
    assert [new["text"][s["start"]:s["end"]] for s in new["extraction"]["presentation"]["spans"]] == ["😀 Clickhere 9", "표시 문자열"]


@pytest.mark.parametrize("name", ["header", "footer", "footNote", "endNote", "drawText", "caption", "hiddenComment", "script", "hyperlink", "delete", "unknownFutureNode"])
def test_legacy_character_policy_includes_all_section_text_and_tail(name):
    raw = archive([("Contents/section0.xml", section(f'<hp:{name} attr="not-content">kept</hp:{name}>tail'))])
    assert extract_hwpx(raw)["text"] == "kept tail"


def test_namespace_and_field_display_url_and_missing_field_end():
    body = '<hp:p><hp:run><hp:ctrl><hp:fieldBegin><hp:parameters><hp:stringParam>https://example.test/secret</hp:stringParam></hp:parameters></hp:fieldBegin></hp:ctrl><hp:t>링크 표시</hp:t></hp:run></hp:p>'
    body += '<p xmlns="urn:other"><fieldBegin><parameters>ordinary text</parameters></fieldBegin></p>'
    text = extract_hwpx(archive([("Contents/section0.xml", section(body))]))["text"]
    assert text == "링크 표시 ordinary text"


def test_original_node_ranges_and_field_tails_across_runs():
    xml = section('<hp:p><hp:run><hp:t>😀 앞</hp:t>'+CONTROL+' tail</hp:run>'
                  '<hp:run><hp:t>표시값</hp:t></hp:run></hp:p>'
                  '<hp:p><hp:run><hp:t>다음 표시값</hp:t><hp:fieldEnd/></hp:run></hp:p>'
                  '<hp:p>'+table("표 값")+CONTROL+'</hp:p>')
    parsed = extract_hwpx(archive([("Contents/section0.xml", xml)]))
    root = ET.fromstring(xml)
    excluded = set(root.findall('.//{*}fieldBegin/{*}parameters'))

    def original_parts(node):
        if node in excluded:
            return
        if node.text:
            yield node.text
        for child in node:
            yield from original_parts(child)
            if child.tail:
                yield child.tail

    for span in parsed["extraction"]["presentation"]["spans"]:
        node = root
        for index in span["locator"].split("#xml=0", 1)[1].split("/")[1:]:
            node = list(node)[int(index)]
        assert parsed["text"][span["start"]:span["end"]] == " ".join(original_parts(node))
    assert "😀 앞  tail 표시값 다음 표시값" in parsed["text"]
    for control in parsed["extraction"]["excluded_controls"]:
        assert 0 <= control["start"] == control["end"] <= len(parsed["text"])
    assert parsed["extraction"]["presentation"]["text_sha256"] == hashlib.sha256(parsed["text"].encode()).hexdigest()


def test_multisection_nested_zip_offsets_and_nested_table_text_once():
    body = f'<hp:p><hp:run>{table("outer",inner=table("😀 inner",ident="nested"))}</hp:run></hp:p>'
    raw = archive([("Contents/section0.xml", section(body)), ("Contents/section1.xml", section('<hp:p><hp:t>다음</hp:t></hp:p>'))])
    parsed = extract_hwpx(raw)
    assert parsed["text"].count("😀 inner") == 1
    tables = parsed["extraction"]["comparison_tables"]
    assert tables[1]["parent_cell"] == tables[0]["cells"][0]["locator"]
    nested = extract_zip(archive([("inner.zip", archive([("doc.hwpx", raw)]))]))
    assert any(nested["text"][s["start"]:s["end"]] == "😀 inner" for s in nested["extraction"]["presentation"]["spans"])


def test_e1_e2_and_edited_baseline_classification():
    raw = sample()
    old, new = extract_hwpx(raw, rule_version=1), extract_hwpx(raw)
    first = compare_document(raw, ".hwpx", old["text"], reference())
    assert first["summary"]["control_groups"] == 1
    assert first["summary"]["content"] == 0
    second = compare_document(raw, ".hwpx", new["text"], reference())
    assert second["summary"]["control_groups"] == 0
    edited = compare_document(raw, ".hwpx", old["text"] + " manually changed", reference())
    assert edited["summary"]["control_groups"] == 0
    assert edited["summary"]["unclassified"] > 0
    assert edited["summary"]["unmatched_tables"] > 0


@pytest.mark.parametrize(("before", "after", "kind"), [
    ("220 V", "220\u00a0V", "whitespace"), ("200 V", "220 V", "content"),
    ("−1,000.25 V", "+1,000.25 V", "content"), ("20 V", "20 A", "content"),
    ("10 이상", "10 이하", "content"), ("A\nB\nC", "C\nA\nB", "content"),
])
def test_difference_preserves_values_and_order(before, after, kind):
    result = diff_text(before, after)
    assert result["completion"] == "complete"
    assert any(c["kind"] == kind for c in result["changes"])
    for c in result["changes"]:
        assert before[c["before_start"]:c["before_end"]] == c["before"]
        assert after[c["after_start"]:c["after_end"]] == c["after"]
    if before.startswith("−"):
        assert result["changes"][0]["before"] == "−1,000.25"


def test_changed_cell_is_not_counted_as_body():
    raw = sample()
    ref = reference("😀 Clickhere 9 본문\n230 V", "230 V")
    result = compare_document(raw, ".hwpx", extract_hwpx(raw)["text"], ref)
    assert result["summary"]["content"] == 0
    assert result["summary"]["changed_cells"] == 1
    assert result["tables"][0]["cells"][0]["changes"]


def test_duplicate_id_invalid_ranges_and_structure_change_are_not_silent():
    raw = sample()
    ref = reference()
    ref["tables"].append(copy.deepcopy(ref["tables"][0]))
    result = compare_document(raw, ".hwpx", extract_hwpx(raw)["text"], ref)
    assert result["summary"]["unmatched_tables"]
    assert "220 V" in result["before_text"]
    ref = reference()
    ref["tables"][0]["cols"] = 2
    ref["tables"][0]["cells"][0]["col_span"] = 2
    result = compare_document(raw, ".hwpx", extract_hwpx(raw)["text"], ref)
    assert result["summary"]["structure_changes"] == 1
    assert result["tables"][0]["row_diff"]


def test_budget_does_not_return_complete():
    assert diff_text("A", "B", budget=Budget(seconds=-1))["completion"] == "truncated"
    assert diff_text("a "*20000, "b "*20000)["completion"] == "truncated"
    result = compare_document(b"", ".hwp", "한"*200000, {"text": "글"*200000, "tables": []})
    assert result["completion"] == "truncated"
    assert result["truncation_reason"] == "detail_output_limit"
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 1_000_000


def test_dependency_direction():
    for name in ("document_comparison", "text_diff", "table_diff", "hwpx_text"):
        text = Path(f"api/parsing/{name}.py").read_text(encoding="utf-8")
        imports = [n.module or "" for n in ast.walk(ast.parse(text)) if isinstance(n, ast.ImportFrom)]
        assert not any("kordoc" in module or module.startswith("api.services") for module in imports)
    for file in Path("frontend/src").rglob("*.*"):
        if file.suffix in {".ts", ".tsx"}:
            assert not re.search(r'from [\'\"]kordoc', file.read_text(encoding="utf-8"))


def test_rule_identity_and_manual_apply_review_policy(client, sqlite_engine, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    prefix = "/v2/notices/RULE-V2"
    assert client.post("/v2/notices", json={"notice_no": "RULE-V2", "title": "Synthetic", "raw": {}}).status_code == 200
    ws = client.post(prefix+"/initialize").json()
    raw = sample()
    path = tmp_path/"doc.hwpx"
    path.write_bytes(raw)
    old = extract_hwpx(raw, rule_version=1)
    inputs = ws["inputs"]
    inputs["documents"] = [{"id": "source", "name": "doc.hwpx", "role": "notice_source",
        "storage_path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "text": old["text"],
        "text_origin": "hwpx", "confirmed": True, "extraction": old["extraction"]},
        {"id": "manual", "role": "notice_source", "name": "manual.hwpx", "text": "keep", "text_origin": "manual_confirmed", "confirmed": True}]
    inputs["requirements"] = [{"id": "req", "text": "source requirement", "document_id": "source", "review_status": "accepted", "compliance": "meets"},
                              {"id": "other", "text": "manual requirement", "document_id": "manual", "review_status": "accepted", "compliance": "meets"}]
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=inputs))
    before = client.get(prefix+"/workspace").json()["inputs"]
    body = {"kind": "extract", "input_version": 1, "idempotency_key": "one"}
    job = client.post(prefix+"/jobs", json=body).json()
    assert client.post(prefix+"/jobs", json={**body, "idempotency_key": "two"}).json()["id"] == job["id"]
    assert run_once(sqlite_engine, lane="external")
    # Merely executing does not modify the input.
    assert client.get(prefix+"/workspace").json()["inputs"] == before
    assert path.read_bytes() == raw
    applied = client.post(prefix+f"/jobs/{job['id']}/apply", json={"version": 1})
    assert applied.status_code == 200, applied.text
    now = applied.json()
    assert now["version"] == 2
    assert now["inputs"]["requirements"][0]["review_status"] == "pending"
    assert now["inputs"]["requirements"][1]["review_status"] == "accepted"
    assert now["inputs"]["documents"][1] == inputs["documents"][1]
    assert client.post(prefix+f"/jobs/{job['id']}/apply", json={"version": 1}).status_code == 409
    assert client.get(prefix+"/workspace").json()["version"] == 2
    # A historic rules-less successful job must not hide the current extraction.
    with sqlite_engine.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.id == job["id"]).values(input_version=2, parameters={"template_key": "bid_form", "visible": False}))
    new_job = client.post(prefix+"/jobs", json={**body, "input_version": 2, "idempotency_key": "new"}).json()
    assert new_job["id"] != job["id"]
    monkeypatch.setattr(document_jobs, "REFERENCE_ENGINE_VERSION", "test-next")
    assert not document_jobs.reusable("document_compare", {"document_identity": "old"}, {"document_identity": "new"})


def test_reference_version_and_stored_body_are_in_identity(client, sqlite_engine, monkeypatch):
    monkeypatch.setenv("WORKSPACE_KORDOC_ENABLED", "true")
    client.post("/v2/notices", json={"notice_no": "IDENTITY", "title": "Synthetic", "raw": {}})
    client.post("/v2/notices/IDENTITY/initialize")
    body = JobRequest(kind="document_compare", input_version=1, idempotency_key="one")
    with sqlite_engine.begin() as conn:
        initial = document_jobs.parameters(conn, "IDENTITY", body)
        monkeypatch.setattr(document_jobs, "REFERENCE_ENGINE_VERSION", "next")
        version = document_jobs.parameters(conn, "IDENTITY", body)
        assert initial["document_identity"] != version["document_identity"]
        inputs = conn.execute(select(workspaces.c.inputs)).scalar_one()
        inputs["documents"].append({"id": "a", "sha256": "fixed", "text": "before"})
        conn.execute(update(workspaces).values(inputs=inputs))
        first = document_jobs.parameters(conn, "IDENTITY", body)
        inputs["documents"][0]["text"] = "after"
        conn.execute(update(workspaces).values(inputs=inputs))
        assert first["document_identity"] != document_jobs.parameters(conn, "IDENTITY", body)["document_identity"]


def test_empty_cell_and_nested_table_are_not_double_counted():
    raw = archive([("Contents/section0.xml", section(table("parent", inner=table("child", ident="nested"))))])
    extracted = extract_hwpx(raw)
    text = extracted["text"]
    ref = {"text": text.replace("child", "CHILD"), "tables": copy.deepcopy(extracted["extraction"]["comparison_tables"])}
    for t in ref["tables"]:
        for c in t["cells"]:
            c["text"] = ref["text"][c["start"]:c["end"]]
    result = compare_document(raw, ".hwpx", text, ref)
    assert result["summary"]["changed_cells"] == 1
    assert result["summary"]["content"] == 0
    assert next(t for t in result["tables"] if t["reference_table_id"] == "table-1")["cells"] == []
    empty = extract_hwpx(archive([("Contents/section0.xml", section('<hp:p>before</hp:p>'+table("")))]))
    c = empty["extraction"]["comparison_tables"][0]["cells"][0]
    assert c["start"] == c["end"] == len("before")


def test_hwp_command_is_unknown_and_never_removed():
    r = compare_document(b"", ".hwp", "ordinary Clickhere:set:42", {"text": "ordinary", "tables": []})
    assert r["summary"]["unclassified"] > 0
    assert "Clickhere" in r["before_text"]
    assert r["summary"]["cells_not_compared"]
