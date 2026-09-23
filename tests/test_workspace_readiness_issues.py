"""Single-source readiness contracts, compatibility and safety invariants."""

import ast
import copy
import json
import re
import zipfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from api.workspace import asset_policy, readiness, service
from api.workspace.executors import execute
from api.workspace.executors.package import run_package
from api.workspace.readiness_issues import (
    CATALOG,
    IssueCode,
    ReadinessIssue,
    issue,
    render_blockers,
)
from api.workspace.tables import reviews
from tests.test_notice_form_package import saved_form_package as _saved_form_package
from tests.test_workspace_v2 import workspace as _workspace

saved_form_package = _saved_form_package
workspace = _workspace

def test_workspace_exposes_typed_reasons_and_get_does_not_change_state(client, sqlite_engine, workspace):
    with sqlite_engine.connect() as conn:
        before = copy.deepcopy(service.load(conn, "E2E-V2"))
        history = list(conn.execute(select(reviews)).mappings())
    result = client.get("/v2/notices/E2E-V2/workspace")
    assert result.status_code == 200
    payload = result.json()
    reasons = [ReadinessIssue.model_validate(value) for value in payload["readiness_issues"]]
    assert payload["blockers"] == render_blockers(reasons)
    assert payload["readiness_checked_at"]
    assert IssueCode.REQUIREMENTS_MISSING in {value.code for value in reasons}
    assert all(value.next_action for value in reasons)
    with sqlite_engine.connect() as conn:
        assert service.load(conn, "E2E-V2") == before
        assert list(conn.execute(select(reviews)).mappings()) == history


def test_scan_extraction_failure_stays_unresolved_and_does_not_mutate_inputs():
    inputs = {"documents": [{"id": "scan", "role": "notice_source", "text": "",
                              "extraction": {"complete": False, "error": "OCR unavailable"}}]}
    before = copy.deepcopy(inputs)
    reasons = readiness.readiness_issues(inputs)
    assert IssueCode.SOURCE_EXTRACTION_REQUIRED in {value.code for value in reasons}
    assert inputs == before
    assert all("원문에 없음" not in value.message for value in reasons)


@pytest.mark.parametrize("details,code", [
    ({"expires_on": "2026-09-20"}, IssueCode.ASSET_EXPIRED),
    ({"no_expiry": True, "subject_business_number": "2222222222"}, IssueCode.ASSET_SUBJECT_MISMATCH),
    ({"no_expiry": True, "stale": True}, IssueCode.ASSET_STALE),
    ({"no_expiry": True, "active": False}, IssueCode.ASSET_DISABLED),
])
def test_invalid_company_asset_blocks_with_specific_reason(monkeypatch, details, code):
    monkeypatch.setattr(asset_policy, "today", lambda: date(2026, 9, 22))
    inputs = {"company": {"business_number": "1111111111"},
              "checklist": [{"id": "proof", "name": "증명"}],
              "documents": [{"id": "doc", "name": "증명서", "role": "company_evidence",
                             "confirmed": True, "text": "evidence", "item_id": "proof",
                             "company_asset": {"subject_business_number": "1111111111", **details}}]}
    reasons = readiness.readiness_issues(inputs)
    match = next(value for value in reasons if value.code == code)
    assert match.entity_id == "doc" and match.blocking
    assert match.message.endswith(": 증명서")
    assert IssueCode.EVIDENCE_UNCONFIRMED in {value.code for value in reasons}
    assert service.blockers(inputs) == render_blockers(reasons)


def test_legacy_dedup_preserves_all_structured_form_locations():
    reasons = [issue(IssueCode.FORM_REVIEW_REQUIRED, "form", key) for key in ("first", "second")]
    assert len(reasons) == 2
    assert render_blockers(reasons) == ["원본 양식 작성값·근거 및 한글 배치 검토 필요"]


def test_portable_reason_does_not_trust_supplied_display_text():
    value = issue(IssueCode.SOURCE_REVIEW_REQUIRED, "notice").model_dump(mode="json")
    value.update(message="준비 완료", next_action="제출하세요")
    parsed = ReadinessIssue.model_validate(value)
    assert parsed.message == "원문 전체 및 필수 요구사항 대조 확인 필요"
    assert parsed.next_action != value["next_action"]


def test_verify_shares_predicates_and_preserves_snapshot(sqlite_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    inputs = {"requirements": [{"id": "r", "text": "납품", "mandatory": True}], "documents": []}
    before = copy.deepcopy(inputs)
    result = execute(sqlite_engine, {"id": "verify", "kind": "verify", "snapshot": inputs, "input_version": 7})
    reasons = [ReadinessIssue.model_validate(value) for value in result["readiness_issues"]]
    assert result["warnings"] == service.blockers(inputs) == render_blockers(reasons)
    assert not result["verified"] and result["readiness_input_version"] == 7
    assert result["readiness_checked_at"] and inputs == before


def test_package_manifest_missing_and_result_share_projection(sqlite_engine, tmp_path, saved_form_package):
    state, _, _ = saved_form_package
    folder = tmp_path / "typed-package"
    folder.mkdir()
    result = run_package(sqlite_engine, {"notice_no": state["notice_no"], "input_version": state["version"],
                                       "snapshot": state["inputs"]}, folder)
    with zipfile.ZipFile(result["artifact"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        reasons = [ReadinessIssue.model_validate(value) for value in manifest["readiness_issues"]]
        warnings = render_blockers(reasons, deduplicate=True)
        assert manifest["warnings"] == result["warnings"] == warnings
        assert result["readiness_issues"] == manifest["readiness_issues"]
        assert archive.read("missing.txt").decode("utf-8") == "\n".join(warnings)
        assert manifest["readiness_checked_at"] == result["readiness_checked_at"]


def test_catalog_and_typescript_contract_cover_every_code():
    assert set(CATALOG) == set(IssueCode)
    source = Path("frontend/src/lib/readiness.ts").read_text(encoding="utf-8")
    codes = re.findall(r'^  \| "([a-z_]+)"', source, re.M)
    assert set(codes) == {value.value for value in IssueCode}
    assert all(template and action for template, action in CATALOG.values())


def test_legacy_blockers_remains_a_projection_not_a_parallel_predicate():
    tree = ast.parse(Path("api/workspace/service.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "blockers")
    assert len(function.body) == 1 and isinstance(function.body[0], ast.Return)
    call = function.body[0].value
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    assert call.func.id == "render_blockers"
