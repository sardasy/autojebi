"""Content budgets and cache regressions; isolated SQLite and no provider traffic."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    select,
    update,
)

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.util import load_python_file
from api.config import settings
from api.workspace import anthropic_client, execution, llm_usage, proposal, service
from api.workspace.tables import budgets, jobs, reviews, workspaces


def inputs():
    return {
        "notice": {"notice_no": "BUDGET", "title": "Original", "close_date": "2026-10-01"},
        "raw": {"original_body": "Full original notice body"},
        "company": {"name": "Test company", "updated_at": "yesterday"},
        "documents": [
            {
                "id": "source",
                "name": "source.pdf",
                "role": "notice_source",
                "text": "Rated voltage 100 V",
                "sha256": "source-bytes",
                "storage_path": "old",
            },
            {
                "id": "evidence",
                "name": "product.pdf",
                "role": "product_evidence",
                "text": "Rated voltage 100 V",
                "sha256": "evidence-bytes",
                "confirmed": True,
            },
        ],
        "requirements": [],
        "proposal_sections": [],
        "source_reviewed": False,
    }


def requirement():
    return {
        "id": "req",
        "text": "Rated voltage",
        "document_id": "source",
        "quote": "100 V",
        "locator": "paragraph 1",
        "category": "technical",
        "mandatory": True,
        "proposed_value": "100 V",
        "evidence_id": "evidence",
        "evidence_quote": "100 V",
        "evidence_locator": "paragraph 1",
        "review_status": "pending",
    }


@pytest.fixture
def state(sqlite_engine, monkeypatch):
    monkeypatch.setattr(settings, "workspace_llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "test-no-network")
    monkeypatch.setattr(settings, "anthropic_model", "test-model")
    monkeypatch.setattr(settings, "proposal_model", "")

    def forbidden(*args, **kwargs):
        pytest.fail("Provider must be mocked explicitly")

    monkeypatch.setattr(anthropic_client.anthropic, "Anthropic", forbidden)
    snapshot = inputs()
    with sqlite_engine.begin() as conn:
        conn.execute(
            workspaces.insert().values(
                notice_no="BUDGET",
                version=1,
                decision="pending",
                inputs=snapshot,
                source_hash="fixture",
                created_at=service.now(),
                updated_at=service.now(),
            )
        )
    return {
        "id": "current",
        "kind": "analyze",
        "notice_no": "BUDGET",
        "input_version": 1,
        "snapshot": snapshot,
    }


def test_gemini_analysis_cache_and_cross_provider_budget(sqlite_engine, state, monkeypatch):
    from api.workspace import gemini

    monkeypatch.setattr(settings, "workspace_llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "no-network")
    monkeypatch.setattr(settings, "gemini_model", "gemini-test")
    calls = []

    def generate(request):
        assert usage(sqlite_engine)[0]["calls"] == 1
        calls.append(request)
        return {"requirements": [{k: v for k, v in requirement().items() if k in {
            "text", "document_id", "quote", "locator", "category", "mandatory",
        }}]}

    monkeypatch.setattr(gemini, "generate", generate)
    result = execution.analyze(sqlite_engine, state)
    assert result["fit_score"] is None
    assert result["llm_usage"]["provider"] == "gemini"
    assert result["llm_usage"]["model"] == "gemini-test"
    previous = completed(sqlite_engine, state, result)
    assert execution.analyze(sqlite_engine, state)["llm_usage"]["reused_from_job_id"] == previous["id"]
    assert len(calls) == 1
    monkeypatch.setattr(settings, "workspace_llm_provider", "anthropic")
    anthropic_calls = []
    mock_provider(monkeypatch, anthropic_calls)
    assert execution.analyze(sqlite_engine, state)["llm_usage"]["provider"] == "anthropic"
    assert len(anthropic_calls) == 1
    assert usage(sqlite_engine)[0]["calls"] == 2
    monkeypatch.setattr(settings, "workspace_llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_model", "gemini-different")
    with pytest.raises(HTTPException, match="llm_budget_exhausted"):
        execution.analyze(sqlite_engine, state)
    assert len(calls) == 1


def test_gemini_missing_key_does_not_fall_back_or_charge(sqlite_engine, state, monkeypatch):
    monkeypatch.setattr(settings, "workspace_llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "")
    with pytest.raises(HTTPException, match="llm_not_configured"):
        execution.analyze(sqlite_engine, state)
    assert usage(sqlite_engine) == []


def test_openai_preserves_cross_provider_limit(sqlite_engine, state, monkeypatch):
    from api.workspace import openai_client

    monkeypatch.setattr(settings, "workspace_llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "no-network")
    llm_usage.reserve_call(sqlite_engine, state)
    llm_usage.reserve_call(sqlite_engine, state)
    monkeypatch.setattr(settings, "workspace_llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "no-network")
    monkeypatch.setattr(openai_client, "generate", lambda _: pytest.fail("No dispatch after budget exhausted"))
    with pytest.raises(HTTPException, match="llm_budget_exhausted"):
        execution.analyze(sqlite_engine, state)
    assert usage(sqlite_engine)[0]["calls"] == 2


def test_openai_missing_key_does_not_use_google_key(sqlite_engine, state, monkeypatch):
    monkeypatch.setattr(settings, "workspace_llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "google_api_key", "other-provider-key")
    with pytest.raises(HTTPException, match="llm_not_configured"):
        execution.analyze(sqlite_engine, state)
    assert usage(sqlite_engine) == []


def test_openai_analysis_cache_and_proposal_review(sqlite_engine, state, monkeypatch):
    from api.workspace import openai_client

    monkeypatch.setattr(settings, "workspace_llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "no-network")
    calls = []

    def generate(request):
        calls.append(request)
        assert usage(sqlite_engine)[0]["calls"] == len(calls)
        if request["payload"]["text"]["format"]["name"] == "requirements":
            return {"requirements": [{k: v for k, v in requirement().items() if k in {
                "text", "document_id", "quote", "locator", "category", "mandatory",
            }}]}
        return {"sections": [{"text": "Rated voltage 999 V", "requirement_ids": ["req"], "evidence_ids": ["evidence"]}]}

    monkeypatch.setattr(openai_client, "generate", generate)
    result = execution.analyze(sqlite_engine, state)
    assert result["fit_score"] is None
    assert result["llm_usage"]["provider"] == "openai"
    previous = completed(sqlite_engine, state, result)
    assert execution.analyze(sqlite_engine, state)["llm_usage"]["reused_from_job_id"] == previous["id"]
    assert len(calls) == 1
    state["kind"] = "proposal"
    state["snapshot"]["requirements"] = [requirement()]
    result = proposal.generate_proposal(sqlite_engine, state)
    assert result["sections"][0]["review_status"] == "pending"
    assert "[검증필요]" in result["sections"][0]["text"]
    assert result["llm_usage"]["provider"] == "openai"
    assert len(calls) == 2


def test_gemini_invalid_quote_keeps_debit(sqlite_engine, state, monkeypatch):
    from api.workspace import gemini

    monkeypatch.setattr(settings, "workspace_llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "no-network")
    monkeypatch.setattr(gemini, "generate", lambda _: {"requirements": [{
        "text": "invented", "document_id": "source", "quote": "not in source",
        "locator": "paragraph 1", "category": "technical", "mandatory": True,
    }]})
    with pytest.raises(HTTPException, match="unverified_quote"):
        execution.analyze(sqlite_engine, state)
    assert usage(sqlite_engine)[0]["calls"] == 1


def test_gemini_proposal_uses_schema_and_human_review(sqlite_engine, state, monkeypatch):
    from api.workspace import gemini

    state["kind"] = "proposal"
    state["snapshot"]["requirements"] = [requirement()]
    monkeypatch.setattr(settings, "workspace_llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "no-network")
    monkeypatch.setattr(settings, "proposal_model", "claude-only-override")

    def generate(request):
        assert request["model"].startswith("gemini-")
        assert "$defs" in request["payload"]["generationConfig"]["responseJsonSchema"]
        return {"sections": [{"text": "Rated voltage 999 V", "requirement_ids": ["req"], "evidence_ids": ["evidence"]}]}

    monkeypatch.setattr(gemini, "generate", generate)
    result = proposal.generate_proposal(sqlite_engine, state)
    assert result["sections"][0]["review_status"] == "pending"
    assert "[검증필요]" in result["sections"][0]["text"]
    assert result["llm_usage"]["provider"] == "gemini"
    assert usage(sqlite_engine)[0]["calls"] == 1


def advance(engine, job, action="decision"):
    with engine.begin() as conn:
        ws = service.load(conn, job["notice_no"])
        updated = service.change(
            conn,
            ws,
            job["snapshot"],
            action,
            "Test review",
            **(
                {"decision": "hold" if ws["decision"] != "hold" else "pending"}
                if action == "decision"
                else {}
            ),
        )
    job["snapshot"] = deepcopy(updated["inputs"])
    job["input_version"] = updated["version"]


def completed(engine, job, result, status="succeeded"):
    record = {
        **job,
        "id": service.uid(),
        "snapshot": deepcopy(job["snapshot"]),
        "idempotency_key": service.uid(),
        "parameters": {},
        "status": status,
        "created_at": service.now(),
        "result": result,
    }
    with engine.begin() as conn:
        conn.execute(jobs.insert().values(**record))
    return record


def usage(engine):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(budgets)).mappings()]


def mock_provider(monkeypatch, calls, invalid=False, raises=False):
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.messages = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create(self, **request):
            calls.append(deepcopy(request))
            if raises:
                raise RuntimeError("Unknown provider outcome")
            name = request["tool_choice"]["name"]
            if name == "requirements":
                result = {
                    "requirements": [
                        {
                            "text": "Rated voltage",
                            "document_id": "source",
                            "quote": "wrong" if invalid else "100 V",
                            "locator": "paragraph 1",
                            "category": "technical",
                            "mandatory": True,
                        }
                    ]
                }
            else:
                result = {
                    "sections": [
                        {
                            "text": "Rated voltage 100 V",
                            "requirement_ids": ["req"],
                            "evidence_ids": ["evidence"],
                        }
                    ]
                }
            return SimpleNamespace(
                content=[SimpleNamespace(type="tool_use", name=name, input=result)]
            )

    monkeypatch.setattr(anthropic_client.anthropic, "Anthropic", Client)


def test_fingerprint_ignores_review_derived_data_and_storage():
    before = inputs()
    after = deepcopy(before)
    after.update(
        decision="hold",
        version=42,
        source_reviewed=True,
        requirements=[requirement()],
        proposal_sections=[{"text": "new derived draft"}],
    )
    after["company"].update(id=42, version=9, updated_at="now")
    after["documents"][0].update(
        id="new-id",
        name="renamed",
        storage_path="elsewhere",
        uploaded_at="now",
        role="company_evidence",
        confirmed=True,
    )
    after["documents"].reverse()
    assert llm_usage.source_input_key(before) == llm_usage.source_input_key(after)


@pytest.mark.parametrize("field", ["raw", "source", "evidence", "company", "notice", "bytes"])
def test_fingerprint_covers_complete_original_and_evidence(field):
    before = inputs()
    before["raw"]["original_body"] = "a" * 200000
    before["documents"][1]["text"] = "b" * 200000
    after = deepcopy(before)
    if field == "raw":
        after["raw"]["original_body"] += "tail"
    elif field in {"source", "evidence"}:
        after["documents"][field == "evidence"]["text"] += "tail"
    elif field == "bytes":
        after["documents"][0]["sha256"] = "new bytes"
    elif field == "company":
        after["company"]["name"] = "Changed company"
    else:
        after["notice"]["close_date"] = "2026-11-01"
    assert llm_usage.source_input_key(before) != llm_usage.source_input_key(after)


def test_same_content_across_decision_review_and_apply_uses_two_total(sqlite_engine, state):
    execution.reserve_call(sqlite_engine, state)
    advance(sqlite_engine, state)
    state["snapshot"]["requirements"] = [requirement()]
    advance(sqlite_engine, state, "apply_result")
    state["snapshot"]["source_reviewed"] = True
    advance(sqlite_engine, state, "source_review")
    state["kind"] = "proposal"
    execution.reserve_call(sqlite_engine, state)
    for _ in range(3):
        advance(sqlite_engine, state)
        with pytest.raises(HTTPException, match="llm_budget_exhausted"):
            execution.reserve_call(sqlite_engine, state)
    rows = usage(sqlite_engine)
    assert sum(r["calls"] for r in rows) == 2
    assert len({r["input_key"] for r in rows}) == 1


def test_legacy_import_api_and_stale_snapshot(sqlite_engine, state):
    assert execution.reserve_call is llm_usage.reserve_call
    execution.reserve_call(sqlite_engine, {"notice_no": "BUDGET", "input_version": 1})
    state["snapshot"]["raw"]["original_body"] = "not synchronized"
    with pytest.raises(HTTPException, match="version_conflict"):
        execution.reserve_call(sqlite_engine, state)
    assert sum(r["calls"] for r in usage(sqlite_engine)) == 1


def test_content_change_new_budget_and_return_to_original_still_exhausted(sqlite_engine, state):
    original = deepcopy(state["snapshot"])
    execution.reserve_call(sqlite_engine, state)
    execution.reserve_call(sqlite_engine, state)
    state["snapshot"]["raw"]["original_body"] += "new corpus"
    advance(sqlite_engine, state)
    execution.reserve_call(sqlite_engine, state)
    execution.reserve_call(sqlite_engine, state)
    state["snapshot"] = original
    advance(sqlite_engine, state)
    with pytest.raises(HTTPException, match="llm_budget_exhausted"):
        execution.reserve_call(sqlite_engine, state)
    assert sum(r["calls"] for r in usage(sqlite_engine)) == 4


def test_legacy_counts_reconcile_without_reset_even_on_exhaustion(sqlite_engine, state):
    for version in (1, 2):
        completed(sqlite_engine, state, None, "failed")
        with sqlite_engine.begin() as conn:
            conn.execute(
                budgets.insert().values(notice_no="BUDGET", input_version=version, calls=2)
            )
        advance(sqlite_engine, state)
    with pytest.raises(HTTPException, match="llm_budget_exhausted"):
        execution.reserve_call(sqlite_engine, state)
    rows = usage(sqlite_engine)
    assert [r["calls"] for r in rows] == [2, 2]
    assert all(r["input_key"] == llm_usage.source_input_key(state["snapshot"]) for r in rows)
    with sqlite_engine.connect() as conn:
        assert len(conn.execute(select(jobs)).all()) == 2


@pytest.mark.parametrize("history", ["missing", "incomplete", "ambiguous"])
def test_unknown_legacy_usage_remains_a_debit_for_all_content(sqlite_engine, state, history):
    if history == "incomplete":
        old = deepcopy(state)
        old["snapshot"] = {"documents": []}
        completed(sqlite_engine, old, None, "failed")
    elif history == "ambiguous":
        completed(sqlite_engine, state, None, "failed")
        old = deepcopy(state)
        old["snapshot"]["raw"]["original_body"] = "conflicting snapshot"
        completed(sqlite_engine, old, None, "failed")
    with sqlite_engine.begin() as conn:
        conn.execute(budgets.insert().values(notice_no="BUDGET", input_version=1, calls=2))
    state["snapshot"]["documents"][0]["text"] += "new content"
    advance(sqlite_engine, state)
    with pytest.raises(HTTPException, match="llm_budget_exhausted"):
        execution.reserve_call(sqlite_engine, state)
    assert usage(sqlite_engine)[0]["input_key"] is None
    assert usage(sqlite_engine)[0]["calls"] == 2


def test_known_legacy_different_content_does_not_debit_new_corpus(sqlite_engine, state):
    completed(sqlite_engine, state, None, "failed")
    original_key = llm_usage.source_input_key(state["snapshot"])
    with sqlite_engine.begin() as conn:
        conn.execute(budgets.insert().values(notice_no="BUDGET", input_version=1, calls=2))
    state["snapshot"]["company"]["name"] = "New company input"
    advance(sqlite_engine, state)
    execution.reserve_call(sqlite_engine, state)
    assert usage(sqlite_engine)[0]["input_key"] == original_key
    assert sum(r["calls"] for r in usage(sqlite_engine)) == 3


def test_analyze_cache_after_apply_and_review_even_without_credentials(
    sqlite_engine, state, monkeypatch
):
    calls = []
    mock_provider(monkeypatch, calls)
    result = execution.analyze(sqlite_engine, state)
    previous = completed(sqlite_engine, state, result)
    state["snapshot"]["requirements"] = [requirement()]
    advance(sqlite_engine, state, "apply_result")
    advance(sqlite_engine, state)
    state["snapshot"]["source_reviewed"] = True
    advance(sqlite_engine, state, "source_review")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    reused = execution.analyze(sqlite_engine, state)
    assert reused["llm_usage"]["reused_from_job_id"] == previous["id"]
    assert reused["requirements"] == result["requirements"]
    assert len(calls) == 1 and sum(r["calls"] for r in usage(sqlite_engine)) == 1
    assert result["llm_usage"]["reused_from_job_id"] is None


@pytest.mark.parametrize("change", ["model", "prompt", "schema", "parameters", "operation"])
def test_cache_requires_exact_request_without_refilling_budget(sqlite_engine, state, change):
    request = {"model": "m", "system": "prompt", "tools": [{"schema": "v1"}], "max_tokens": 100}
    result = {
        "requirements": [{k: v for k, v in requirement().items() if k != "id"}],
        "llm_usage": llm_usage.result_metadata(state, request),
    }
    completed(sqlite_engine, state, result)
    execution.reserve_call(sqlite_engine, state)
    execution.reserve_call(sqlite_engine, state)
    assert llm_usage.reuse_result(sqlite_engine, state, request)
    changed = deepcopy(request)
    if change == "model":
        changed["model"] = "new"
    elif change == "prompt":
        changed["system"] = "new"
    elif change == "schema":
        changed["tools"] = [{"schema": "new"}]
    elif change == "parameters":
        changed["max_tokens"] = 200
    else:
        state["kind"] = "proposal"
    assert llm_usage.reuse_result(sqlite_engine, state, changed) is None
    with pytest.raises(HTTPException, match="llm_budget_exhausted"):
        execution.reserve_call(sqlite_engine, state)


@pytest.mark.parametrize("bad", ["quote", "document", "empty", "failed", "legacy"])
def test_invalid_or_incomplete_analysis_never_reused(sqlite_engine, state, monkeypatch, bad):
    calls = []
    mock_provider(monkeypatch, calls)
    result = execution.analyze(sqlite_engine, state)
    if bad == "quote":
        result["requirements"][0]["quote"] = "not in original"
    elif bad == "document":
        result["requirements"][0]["document_id"] = "missing"
    elif bad == "empty":
        result["requirements"] = []
    elif bad == "legacy":
        result.pop("llm_usage")
    completed(sqlite_engine, state, result, "failed" if bad == "failed" else "succeeded")
    advance(sqlite_engine, state)
    execution.analyze(sqlite_engine, state)
    assert len(calls) == 2


def test_failed_provider_dispatch_is_not_refunded(sqlite_engine, state, monkeypatch):
    calls = []
    mock_provider(monkeypatch, calls, raises=True)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            execution.analyze(sqlite_engine, state)
        advance(sqlite_engine, state)
    with pytest.raises(HTTPException, match="llm_budget_exhausted"):
        execution.analyze(sqlite_engine, state)
    assert len(calls) == 2


def test_proposal_cache_ignores_requirement_review_but_keeps_bindings(
    sqlite_engine, state, monkeypatch
):
    calls = []
    mock_provider(monkeypatch, calls)
    state["kind"] = "proposal"
    state["snapshot"]["requirements"] = [requirement()]
    advance(sqlite_engine, state)
    result = proposal.generate_proposal(sqlite_engine, state)
    previous = completed(sqlite_engine, state, result)
    state["snapshot"]["requirements"][0]["review_status"] = "accepted"
    advance(sqlite_engine, state, "requirement_review")
    reused = proposal.generate_proposal(sqlite_engine, state)
    assert reused["llm_usage"]["reused_from_job_id"] == previous["id"]
    state["snapshot"]["requirements"][0]["proposed_value"] = "Different proposal"
    advance(sqlite_engine, state, "requirement_review")
    proposal.generate_proposal(sqlite_engine, state)
    assert len(calls) == 2
    assert len({r["input_key"] for r in usage(sqlite_engine)}) == 1


@pytest.mark.parametrize("bad", ["requirement", "evidence", "binding", "quote"])
def test_proposal_cache_rejects_invalid_citations(sqlite_engine, state, monkeypatch, bad):
    calls = []
    mock_provider(monkeypatch, calls)
    state["kind"] = "proposal"
    state["snapshot"]["requirements"] = [requirement()]
    advance(sqlite_engine, state)
    result = proposal.generate_proposal(sqlite_engine, state)
    if bad == "requirement":
        result["sections"][0]["requirement_ids"] = ["unknown"]
    elif bad == "evidence":
        result["sections"][0]["evidence_ids"] = ["source"]
    elif bad == "binding":
        result["sections"][0]["evidence_ids"] = []
    else:
        state["snapshot"]["requirements"][0]["evidence_quote"] = "invalid quote"
        result["llm_usage"] = llm_usage.result_metadata(state, calls[0])
    completed(sqlite_engine, state, result)
    assert llm_usage.reuse_result(sqlite_engine, state, calls[0]) is None


@pytest.mark.parametrize("kind", ["analyze", "proposal", "proposal_without_evidence", "grade"])
def test_execute_and_cache_preserve_accepted_inputs_and_history(
    sqlite_engine, state, monkeypatch, tmp_path, kind
):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    if kind == "grade":
        from api.workspace import grading

        monkeypatch.setattr(grading, "_sku_references", lambda *args: {"reason": "test references", "candidates": [], "warnings": []})
        monkeypatch.setattr(grading, "_qualification_references", lambda *args: {"reason": "test references", "warnings": []})
    calls = []
    mock_provider(monkeypatch, calls)
    state["kind"] = "proposal" if kind == "proposal_without_evidence" else kind
    state["snapshot"]["requirements"] = [{**requirement(), "review_status": "accepted"}]
    state["snapshot"]["proposal_sections"] = [
        {"id": "approved", "text": "Human edit", "review_status": "approved",
         "requirement_ids": ["req"], "evidence_ids": ["evidence"]}
    ]
    if kind == "proposal_without_evidence":
        state["snapshot"]["documents"][1]["confirmed"] = False
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=deepcopy(state["snapshot"])))
    completed(sqlite_engine, state, {"warnings": [], "message": "Previous normal result"})

    previous = None
    for _ in range(2):
        before = deepcopy(state)
        with sqlite_engine.connect() as conn:
            saved_workspace = dict(conn.execute(select(workspaces)).mappings().one())
            saved_jobs = [dict(r) for r in conn.execute(select(jobs)).mappings()]
            saved_reviews = [dict(r) for r in conn.execute(select(reviews)).mappings()]

        result = execution.execute(sqlite_engine, state)

        assert state == before
        with sqlite_engine.connect() as conn:
            assert dict(conn.execute(select(workspaces)).mappings().one()) == saved_workspace
            assert [dict(r) for r in conn.execute(select(jobs)).mappings()] == saved_jobs
            assert [dict(r) for r in conn.execute(select(reviews)).mappings()] == saved_reviews
        if kind in {"analyze", "proposal"}:
            assert result["llm_usage"]["reused_from_job_id"] == (
                previous["id"] if previous else None
            )
            assert len(calls) == 1
            assert sum(r["calls"] for r in usage(sqlite_engine)) == 1
        else:
            assert calls == [] and usage(sqlite_engine) == []
        if previous is None:
            previous = completed(sqlite_engine, state, result)
            advance(sqlite_engine, state)


def test_migration_adds_nullable_key_and_downgrade_preserves_counters(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    meta = MetaData()
    legacy = Table(
        "workspace_llm_budgets",
        meta,
        Column("notice_no", String, primary_key=True),
        Column("input_version", Integer, primary_key=True),
        Column("calls", Integer),
    )
    meta.create_all(engine)
    migration = load_python_file(
        str(Path(__file__).resolve().parents[1] / "alembic" / "versions"),
        "0014_workspace_llm_inputs.py",
    )
    with engine.begin() as conn:
        conn.execute(legacy.insert().values(notice_no="OLD", input_version=7, calls=2))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(conn)))
        migration.upgrade()
        columns = {c["name"]: c for c in inspect(conn).get_columns(legacy.name)}
        assert columns["input_key"]["nullable"] is True
        assert any(
            i["name"] == "workspace_llm_input_key" for i in inspect(conn).get_indexes(legacy.name)
        )
        assert conn.execute(select(legacy.c.calls)).scalar_one() == 2
        migration.downgrade()
        assert "input_key" not in {c["name"] for c in inspect(conn).get_columns(legacy.name)}
        assert conn.execute(select(legacy.c.calls)).scalar_one() == 2
