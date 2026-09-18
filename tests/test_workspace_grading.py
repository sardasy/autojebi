"""Contract tests for snapshot grading, with no network, LLM, or state mutations."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import event, insert, select

from api.grading.schemas import QualificationInfo
from api.routers.notices import bid_pipeline
from api.sku.schemas import AbbSku, SkuMatch
from api.workspace import grading
from api.workspace.tables import workspaces


def requirement(key: str = "technical", **changes) -> dict:
    return {
        "id": key,
        "category": key,
        "text": "A human summary; never an invented SKU query",
        "document_id": "source",
        "quote": "Original technical requirement" if key == "technical" else "License requirement",
        "locator": "p1",
        "mandatory": True,
        "review_status": "accepted",
        "compliance": "meets",
        "evidence_id": "evidence",
        "evidence_quote": "Confirmed product and company facts",
        "evidence_locator": "p2",
        "proposed_value": "Explicit human assessment",
        **changes,
    }


@pytest.fixture
def job():
    return {
        "notice_no": "GRADING-000",
        "input_version": 3,
        "snapshot": {
            "notice": {"bid_no": "GRADING", "bid_seq": "000", "base_price": 1200},
            "documents": [
                {
                    "id": "source",
                    "role": "notice_source",
                    "text": "Original technical requirement. License requirement.",
                },
                {
                    "id": "evidence",
                    "role": "product_evidence",
                    "confirmed": True,
                    "text": "Confirmed product and company facts. Total offer KRW 1,000.",
                },
            ],
            "requirements": [requirement(), requirement("qualification")],
            "commercial": {
                "offer_price": 1000.0,
                "quantity": 3,
                "document_id": "evidence",
                "quote": "Total offer KRW 1,000",
                "locator": "p3",
                "note": "Total, not unit price",
            },
        },
    }


@pytest.fixture(autouse=True)
def external(monkeypatch):
    store = SimpleNamespace(
        collection="verified_sku_corpus",
        collection_exists=Mock(return_value=True),
        search=Mock(return_value=[]),
        _client=SimpleNamespace(close=Mock()),
    )
    client = SimpleNamespace(
        fetch_qualifications=AsyncMock(
            return_value=QualificationInfo(bid_no="GRADING", bid_seq="000")
        ),
        aclose=AsyncMock(),
    )
    store_factory, client_factory = Mock(return_value=store), Mock(return_value=client)
    monkeypatch.setattr(grading, "QdrantStore", store_factory)
    monkeypatch.setattr(grading, "G2BClient", client_factory)
    monkeypatch.setattr(grading.settings, "data_go_kr_api_key", "")
    return SimpleNamespace(
        store=store, client=client, store_factory=store_factory, client_factory=client_factory
    )


def test_complete_contract_combines_only_explicit_assessments(job, monkeypatch):
    combine = Mock(wraps=grading.combine)
    monkeypatch.setattr(grading, "combine", combine)
    result = grading.grade(object(), job)
    combine.assert_called_once_with(1.0, 1.0, 1.0)
    assert result["fit_score"] == result["score_total"] == pytest.approx(1.0)
    assert result["score_scale"] == "0..1"
    assert result["score_spec"] == result["qualification_score"] == result["price_score"] == 1.0
    assert result["technical_coverage"] == result["technical_assessment_coverage"] == 1.0
    assert all(axis["state"] == "evaluated" and axis["reason"] for axis in result["axes"].values())
    assert result["axes"]["price"]["basis"] == "total_offer_vs_notice_base_price"
    assert result["axes"]["price"]["quantity"] == 3
    assert result["axes"]["price"]["source"]["quote"] == job["snapshot"]["commercial"]["quote"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "category,key", [("technical", "score_spec"), ("qualification", "qualification_score")]
)
def test_missing_compliance_is_not_a_pass(job, category, key, monkeypatch):
    req = next(r for r in job["snapshot"]["requirements"] if r["category"] == category)
    req.pop("compliance")
    combine = Mock(side_effect=AssertionError("must not combine partial axes"))
    monkeypatch.setattr(grading, "combine", combine)
    result = grading.grade(None, job)
    assert result[key] is None and result["fit_score"] is None
    if category == "technical":
        assert result["technical_coverage"] == 1.0
        assert result["technical_assessment_coverage"] == 0.0
    combine.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("review_status", "pending"),
        ("review_status", "rejected"),
        ("quote", "not in source"),
        ("locator", ""),
        ("document_id", "missing"),
        ("evidence_quote", "not in evidence"),
        ("evidence_locator", ""),
        ("proposed_value", ""),
        ("evidence_id", "source"),
        ("compliance", "unassessed"),
        ("compliance", "unknown"),
    ],
)
def test_invalid_provenance_or_pending_compliance_cannot_score(job, field, value):
    job["snapshot"]["requirements"][0][field] = value
    result = grading.grade(None, job)
    assert result["score_spec"] is None and result["fit_score"] is None
    assert result["axes"]["spec"]["unassessed_requirements"][0]["requirement_id"] == "technical"


def test_unconfirmed_evidence_cannot_score_either_axis_or_price(job):
    job["snapshot"]["documents"][1]["confirmed"] = False
    result = grading.grade(None, job)
    assert result["score_spec"] is result["qualification_score"] is result["price_score"] is None
    assert result["technical_coverage"] == 0.0


@pytest.mark.parametrize(
    "category,key", [("technical", "score_spec"), ("qualification", "qualification_score")]
)
def test_all_requirements_must_be_assessed_before_axis_scoring(job, category, key):
    first = next(r for r in job["snapshot"]["requirements"] if r["category"] == category)
    first["compliance"] = "does_not_meet"
    job["snapshot"]["requirements"].append({**first, "id": "pending", "compliance": "unassessed"})
    result = grading.grade(None, job)
    assert result[key] is None


@pytest.mark.parametrize(
    "category,key", [("technical", "score_spec"), ("qualification", "qualification_score")]
)
def test_mandatory_noncompliance_gates_axis_to_zero(job, category, key):
    first = next(r for r in job["snapshot"]["requirements"] if r["category"] == category)
    job["snapshot"]["requirements"].append({**first, "id": "failed", "compliance": "does_not_meet"})
    result = grading.grade(None, job)
    assert result[key] == 0.0
    assert (
        result["axes"]["spec" if category == "technical" else "qualification"]["reason_code"]
        == "mandatory_not_met"
    )


@pytest.mark.parametrize(
    "category,key", [("technical", "score_spec"), ("qualification", "qualification_score")]
)
def test_optional_noncompliance_uses_explicit_ratio(job, category, key):
    first = next(r for r in job["snapshot"]["requirements"] if r["category"] == category)
    job["snapshot"]["requirements"].append(
        {**first, "id": "optional", "mandatory": False, "compliance": "does_not_meet"}
    )
    result = grading.grade(None, job)
    assert result[key] == 0.5


def test_missing_axes_are_none_and_document_requirements_do_not_inflate_coverage(job):
    job["snapshot"]["requirements"] = [requirement("document"), requirement("schedule")]
    job["snapshot"].pop("commercial")
    result = grading.grade(None, job)
    for key in (
        "score_spec",
        "qualification_score",
        "price_score",
        "fit_score",
        "technical_coverage",
    ):
        assert result[key] is None
    assert result["warnings"]


def test_sku_queries_are_verified_original_quotes_and_similarity_is_not_fit(job, external):
    external.store.search.return_value = [
        SkuMatch(
            sku=AbbSku(
                sku_id="catalog-1",
                name="Catalog item",
                category="product",
                description="Verified corpus entry",
            ),
            score=0.999,
        )
    ]
    job["snapshot"]["requirements"][0]["compliance"] = "does_not_meet"
    result = grading.grade(None, job)
    external.store.search.assert_called_once_with("Original technical requirement", limit=5)
    assert result["score_spec"] == 0.0
    assert result["candidates"][0]["similarity"] == 0.999
    assert result["candidates"][0]["source"] == {
        "type": "qdrant",
        "collection": "verified_sku_corpus",
        "query": "Original technical requirement",
        "quote": "Original technical requirement",
        "document_id": "source",
        "locator": "p1",
        "requirement_id": "technical",
    }
    assert result["candidates"][0]["review_status"] == "pending"
    external.store._client.close.assert_called_once()


def test_search_queries_and_candidates_are_bounded(job, external):
    reqs = [requirement(id=str(i), quote=f"Original requirement {i}") for i in range(8)]
    job["snapshot"]["requirements"] = reqs
    job["snapshot"]["documents"][0]["text"] = "\n".join(r["quote"] for r in reqs)
    external.store.search.return_value = [
        SkuMatch(
            sku=AbbSku(sku_id=str(i), name="Item", category="product", description="Catalog"),
            score=i / 10,
        )
        for i in range(8)
    ]
    result = grading.grade(None, job)
    assert external.store.search.call_count == 5
    assert all(call.kwargs["limit"] == 5 for call in external.store.search.call_args_list)
    assert len(result["candidates"]) == 5
    assert result["sku_search"]["omitted_query_count"] == 3
    assert result["sku_search"]["warnings"]


def test_invalid_source_never_triggers_generic_sku_search(job, external):
    job["snapshot"]["requirements"][0]["quote"] = "not in source"
    result = grading.grade(None, job)
    external.store_factory.assert_not_called()
    assert result["sku_search"]["state"] == "not_queried"


@pytest.mark.parametrize(
    "failure", ["constructor", "collection_false", "collection_exception", "search"]
)
def test_sku_failure_is_sanitized_unavailable(job, external, failure):
    error = RuntimeError("secret-key https://private.invalid/?token=secret")
    if failure == "constructor":
        external.store_factory.side_effect = error
    elif failure == "collection_false":
        external.store.collection_exists.return_value = False
    elif failure == "collection_exception":
        external.store.collection_exists.side_effect = error
    else:
        external.store.search.side_effect = error
    result = grading.grade(None, job)
    assert result["sku_search"]["state"] == "unavailable"
    assert result["candidates"] == []
    assert "secret" not in json.dumps(result)
    if failure != "constructor":
        external.store._client.close.assert_called_once()


def test_empty_success_is_distinct_from_search_failure(job):
    result = grading.grade(None, job)
    assert result["sku_search"]["state"] == "no_matches"
    assert result["score_spec"] == 1.0


def test_partial_search_failure_does_not_return_empty_or_partial_success(job, external):
    job["snapshot"]["requirements"].append(requirement(id="extra", quote="License requirement"))
    external.store.search.side_effect = [[], RuntimeError("secret")]
    result = grading.grade(None, job)
    assert result["sku_search"]["state"] == "unavailable"
    external.store._client.close.assert_called_once()


def test_g2b_key_absent_does_not_call_client(job, external):
    result = grading.grade(None, job)
    external.client_factory.assert_not_called()
    assert result["qualification_references"]["state"] == "not_configured"


@pytest.mark.parametrize("bid_seq", [None, "", 0])
def test_g2b_never_guesses_notice_sequence(job, external, monkeypatch, bid_seq):
    monkeypatch.setattr(grading.settings, "data_go_kr_api_key", "test-key")
    job["snapshot"]["notice"]["bid_seq"] = bid_seq
    job["snapshot"]["raw"] = {"bidNtceOrd": "000"}
    result = grading.grade(None, job)
    external.client_factory.assert_not_called()
    assert result["qualification_references"]["reason_code"] == "notice_identity_missing"


@pytest.mark.parametrize("licenses", [[], ["License reference"]])
def test_g2b_exact_identity_and_references_never_auto_pass(job, external, monkeypatch, licenses):
    monkeypatch.setattr(grading.settings, "data_go_kr_api_key", "test-key")
    external.client.fetch_qualifications.return_value = QualificationInfo(
        bid_no="GRADING",
        bid_seq="000",
        licenses=licenses,
    )
    job["snapshot"]["requirements"] = [requirement()]
    result = grading.grade(None, job)
    external.client.fetch_qualifications.assert_awaited_once_with("GRADING", "000")
    external.client.aclose.assert_awaited_once()
    assert result["qualification_score"] is None
    refs = result["qualification_references"]
    assert refs["review_status"] == "pending"
    assert refs["state"] == ("pending_human_confirmation" if licenses else "no_references")
    assert refs["references"]["licenses"] == licenses


@pytest.mark.parametrize(
    "failure", ["constructor", "exception", "returned_error", "wrong_identity"]
)
def test_qualification_failures_are_explicit_without_legacy_heuristic(
    job, external, monkeypatch, failure
):
    monkeypatch.setattr(grading.settings, "data_go_kr_api_key", "test-key")
    job["snapshot"]["requirements"] = [requirement()]
    job["snapshot"]["raw"] = {"cntrctCnclsMthdNm": "unrestricted", "bidQlfctRgstDt": "29991231"}
    if failure == "constructor":
        external.client_factory.side_effect = RuntimeError("secret")
    elif failure == "exception":
        external.client.fetch_qualifications.side_effect = RuntimeError("secret")
    else:
        external.client.fetch_qualifications.return_value = QualificationInfo(
            bid_no="wrong" if failure == "wrong_identity" else "GRADING",
            bid_seq="000",
            error="secret" if failure == "returned_error" else None,
        )
    result = grading.grade(None, job)
    assert result["qualification_score"] is None
    assert result["qualification_references"]["state"] == "unavailable"
    assert result["qualification_references"]["references"] is None
    assert "secret" not in json.dumps(result)
    if failure != "constructor":
        external.client.aclose.assert_awaited_once()


def test_active_event_loop_is_explicit_unavailable_not_a_leaked_coroutine(
    job, monkeypatch, external
):
    monkeypatch.setattr(grading.settings, "data_go_kr_api_key", "test-key")

    async def run():
        return grading.grade(None, job)

    result = asyncio.run(run())
    assert result["qualification_references"]["state"] == "unavailable"
    external.client_factory.assert_not_called()


@pytest.mark.parametrize(
    "quote",
    [
        "KRW 1,000",
        "KRW 1000.00",
        "1,000원",
        "1,000.0 원",
        "₩1000",
        "총액 1000원 (부가세 포함)",
        "Total KRW 1,000.",
    ],
)
def test_price_requires_exact_positive_won_amount(job, quote):
    job["snapshot"]["commercial"]["quote"] = quote
    job["snapshot"]["documents"][1]["text"] += " " + quote
    assert grading.grade(None, job)["price_score"] == 1.0


@pytest.mark.parametrize(
    "quote",
    [
        "KRW 11,000",
        "KRW 1000.50",
        "KRW 1,00",
        "KRW 1,000,00",
        "KRW 10000",
        "USD 1,000",
        "$1,000",
        "1,000",
        "1000만원",
        "KRW 1000 million",
        "-1000원",
        "- 1000원",
        "1000.5원",
        "1000원2",
        "1e1000원",
        "1/1000원",
        "KRW 1000 000",
        "1 1000원",
        "\u22121000원",
        "\uff0d1000원",
        "KRW 1000 %",
        "USD 1000원",
    ],
)
def test_price_rejects_substrings_malformed_currency_and_scaled_values(job, quote):
    job["snapshot"]["commercial"]["quote"] = quote
    job["snapshot"]["documents"][1]["text"] += " " + quote
    result = grading.grade(None, job)
    assert result["price_score"] is None
    assert result["axes"]["price"]["reason_code"] == "offer_quote_mismatch"


@pytest.mark.parametrize(
    "field,value",
    [
        ("offer_price", 0),
        ("offer_price", -1),
        ("offer_price", float("nan")),
        ("offer_price", float("inf")),
        ("offer_price", True),
        ("quantity", 0),
        ("quantity", -1),
        ("quantity", 1.5),
        ("quantity", True),
        ("document_id", "source"),
        ("document_id", "missing"),
        ("locator", ""),
        ("quote", ""),
        ("quote", "absent quote KRW 1000"),
    ],
)
def test_missing_or_invalid_commercial_evidence_stays_unassessed(job, field, value):
    job["snapshot"]["commercial"][field] = value
    result = grading.grade(None, job)
    assert result["price_score"] is None and result["fit_score"] is None


@pytest.mark.parametrize("base", [None, 0, -100, float("nan"), float("inf"), True])
def test_price_never_uses_raw_budget_fallback(job, base):
    job["snapshot"]["notice"]["base_price"] = base
    job["snapshot"]["raw"] = {"bssamt": 10000, "asignBdgtAmt": 10000}
    assert grading.grade(None, job)["price_score"] is None


@pytest.mark.parametrize("base,score", [(999, 0.0), (1000, 1.0), (1001, 1.0)])
def test_price_is_transparent_total_budget_check_not_quantity_estimate(job, base, score):
    job["snapshot"]["notice"]["base_price"] = base
    result = grading.grade(None, job)
    assert result["price_score"] == score
    assert result["axes"]["price"]["offer_price"] == 1000


def test_close_failures_are_sanitized_without_losing_assessment(job, external, monkeypatch):
    monkeypatch.setattr(grading.settings, "data_go_kr_api_key", "test-key")
    external.store._client.close.side_effect = RuntimeError("secret")
    external.client.aclose.side_effect = RuntimeError("secret")
    result = grading.grade(None, job)
    assert result["sku_search"]["warnings"] and result["qualification_references"]["warnings"]
    assert result["fit_score"] == pytest.approx(1.0)
    assert "secret" not in json.dumps(result)


def test_grade_preserves_snapshot_legacy_status_and_workspace_decision(job, sqlite_engine):
    original = deepcopy(job)
    stamp = datetime.now(UTC)
    with sqlite_engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(notice_no=job["notice_no"], status="analyzed", fit_score=73)
        )
        conn.execute(
            insert(workspaces).values(
                notice_no=job["notice_no"],
                decision="hold",
                inputs=job["snapshot"],
                source_hash="fixture",
                created_at=stamp,
                updated_at=stamp,
            )
        )
    statements = []

    def record_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(sqlite_engine, "before_cursor_execute", record_sql)
    try:
        grading.grade(sqlite_engine, job)
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", record_sql)
    assert statements == []
    assert job == original
    with sqlite_engine.connect() as conn:
        legacy = (
            conn.execute(select(bid_pipeline).where(bid_pipeline.c.notice_no == job["notice_no"]))
            .mappings()
            .one()
        )
        workspace = (
            conn.execute(select(workspaces).where(workspaces.c.notice_no == job["notice_no"]))
            .mappings()
            .one()
        )
    assert legacy["status"] == "analyzed" and legacy["fit_score"] == 73
    assert workspace["decision"] == "hold" and workspace["inputs"] == original["snapshot"]
