"""Exact deterministic hints never approve, call models, or alter source text."""

import hashlib
import json

import pytest
from sqlalchemy import select, update

from api.routers.notices import bid_pipeline
from api.workspace.requirement_candidates import MAX_CANDIDATES, MAX_CHARACTERS, find_candidates
from api.workspace.tables import jobs, reviews, workspaces


def source(text, **extra):
    return {"id": "source", "name": "공고", "role": "notice_source", "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(), **extra}


def test_exact_quotes_preserve_numbers_negation_conditions_unicode_and_hashes():
    text = "📌 일반 안내\r\n  수량 3대, 단 예비 장비 1대는 포함하지 않는다.\r\n제출서류: 사업자등록증\n납기는 계약일로부터 90일 이내이다.\n면허를 보유하여야 한다."
    result = find_candidates({"documents": [source(text)]}, 7)
    assert result.version == 7 and len(result.items) == 4
    for item in result.items:
        assert item.text == item.quote == text[item.start:item.end]
        assert item.source_text_sha256 == hashlib.sha256(text.encode()).hexdigest()
        assert item.document_sha256 == source(text)["sha256"]
        assert "review_status" not in item.model_dump() and "compliance" not in item.model_dump()
    assert result.items[0].quote == "수량 3대, 단 예비 장비 1대는 포함하지 않는다."
    assert result.items[0].start == text.index("수량")
    assert "2행" in result.items[0].locator
    assert [item.category for item in result.items] == ["technical", "document", "schedule", "qualification"]


def test_ignores_reference_material_and_general_prose_and_is_deterministic():
    docs = [source("회사 소개입니다.\n안내 문서를 참고하세요."), source("제출서류: 견적서", id="reference", role="company_reference")]
    assert find_candidates({"documents": docs}, 3).items == []
    inputs = {"documents": [source("수량 3대\n수량 3대")]}
    first = find_candidates(inputs, 3)
    assert first == find_candidates(inputs, 3)
    assert first.items[0].id != first.items[1].id


def test_explicit_calendar_deadlines_and_incomplete_extraction_are_disclosed():
    quote = "제출 마감: 2026-09-30 10:00 (연장 불가)"
    result = find_candidates({"documents": [source(quote, extraction={"complete": False})]}, 1)
    assert result.items[0].quote == quote and result.items[0].category == "schedule"
    assert any("추출이 끝나지 않은" in warning for warning in result.warnings)


def test_caps_candidates_and_skips_long_or_cut_off_lines_without_losing_negation():
    many = "\n".join(f"납품 수량 {n}대" for n in range(MAX_CANDIDATES + 5))
    limited = find_candidates({"documents": [source(many)]}, 1)
    assert len(limited.items) == MAX_CANDIDATES and limited.limited
    prefix = "일반 안내\n" * 10000
    long_line = "x" * (MAX_CHARACTERS - len(prefix) - 4) + "제출 필수 아님"
    truncated = find_candidates({"documents": [source(prefix + long_line)]}, 1)
    assert truncated.scanned_characters == MAX_CHARACTERS
    assert truncated.limited and not truncated.items
    long_result = find_candidates({"documents": [source("수량 3대 " + "x" * 4000)]}, 1)
    assert not long_result.items and any("4,000" in warning for warning in long_result.warnings)


def test_total_character_limit_applies_across_documents_and_missing_hash_is_disclosed():
    result = find_candidates({"documents": [source("일반 안내\n" * 20000), source("납품 수량 3대\n" * 10000, id="second", sha256=None)]}, 1)
    assert result.scanned_characters <= MAX_CHARACTERS
    assert result.limited and any("파일 해시" in warning for warning in result.warnings)
    assert find_candidates({"documents": [source("")]}, 1).warnings


@pytest.fixture
def candidate_workspace(client, sqlite_engine, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKSPACE_AUTH_ENABLED", "false")
    assert client.post("/v2/notices", json={"notice_no": "E2E-CANDIDATES", "title": "Candidate test", "source": "MANUAL_E2E", "raw": {}}).status_code == 200
    assert client.post("/v2/notices/E2E-CANDIDATES/initialize").status_code == 200
    text = "수량 3대, 제외 조건 없음.\n납품 기한은 계약일로부터 90일 이내이다."
    path = tmp_path / "source.txt"
    path.write_bytes(text.encode())
    with sqlite_engine.begin() as conn:
        inputs = conn.execute(select(workspaces.c.inputs).where(workspaces.c.notice_no == "E2E-CANDIDATES")).scalar_one()
        inputs["documents"] = [source(text, storage_path=str(path))]
        conn.execute(update(workspaces).where(workspaces.c.notice_no == "E2E-CANDIDATES").values(inputs=inputs))
    return path


def test_api_exposes_source_fields_without_writes_or_model_calls(client, sqlite_engine, candidate_workspace, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Candidate discovery must not call models or change the workspace")
    monkeypatch.setattr("api.workspace.providers.generate", forbidden)
    monkeypatch.setattr("api.workspace.service.change", forbidden)
    with sqlite_engine.connect() as conn:
        before_jobs = conn.execute(select(jobs)).mappings().all()
        before_reviews = conn.execute(select(reviews)).mappings().all()
    response = client.get("/v2/notices/E2E-CANDIDATES/requirement-candidates?version=1")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["version"] == 1 and len(result["items"]) == 2
    item = result["items"][0]
    assert {"document_sha256", "source_text_sha256", "start", "end", "quote", "locator"} <= item.keys()
    assert item["quote"] == "수량 3대, 제외 조건 없음."
    assert "storage_path" not in response.text
    with sqlite_engine.connect() as conn:
        assert conn.execute(select(jobs)).mappings().all() == before_jobs
        assert conn.execute(select(reviews)).mappings().all() == before_reviews
    assert client.get("/v2/notices/E2E-CANDIDATES/requirement-candidates?version=2").status_code == 409
    candidate_workspace.write_bytes(b"changed")
    stale = client.get("/v2/notices/E2E-CANDIDATES/requirement-candidates?version=1")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "source_file_changed"


def test_candidate_api_requires_personal_identity_and_detects_changed_notice(client, sqlite_engine, candidate_workspace, monkeypatch):
    token = "fixture-candidate-reader-" + "x" * 40
    monkeypatch.setenv("WORKSPACE_AUTH_ENABLED", "true")
    monkeypatch.setenv("WORKSPACE_AUTH_USERS", json.dumps([{
        "id": "candidate-reader", "name": "Candidate Reader", "role": "viewer",
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    }]))
    monkeypatch.setenv("WORKSPACE_AUTH_REGISTRY", "")
    path = "/v2/notices/E2E-CANDIDATES/requirement-candidates?version=1"
    assert client.get(path).status_code == 401
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(path, headers=headers).status_code == 200
    with sqlite_engine.begin() as conn:
        conn.execute(update(bid_pipeline).where(bid_pipeline.c.notice_no == "E2E-CANDIDATES").values(title="Changed notice"))
    response = client.get(path, headers=headers)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "source_changed"
