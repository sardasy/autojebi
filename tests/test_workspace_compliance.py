"""Manual compliance and commercial provenance; isolated DB and no paid calls."""

from copy import deepcopy

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update

from api.workspace import service
from api.workspace.models import CommercialRequest
from api.workspace.provenance import proposal_coverage, requirement_valid, section_valid
from api.workspace.tables import budgets, jobs, reviews, workspaces


def manual_inputs():
    return {
        "source_reviewed": True,
        "checklist": [],
        "documents": [
            {"id": "source", "role": "notice_source", "text": "Required rating 100 V"},
            {
                "id": "evidence",
                "role": "product_evidence",
                "confirmed": True,
                "text": "Rated 100 V. Total KRW 1,000.",
            },
        ],
        "requirements": [
            {
                "id": "req",
                "text": "Rating",
                "document_id": "source",
                "quote": "100 V",
                "locator": "p1",
                "category": "technical",
                "mandatory": True,
                "proposed_value": "100 V",
                "evidence_id": "evidence",
                "evidence_quote": "100 V",
                "evidence_locator": "p1",
                "review_status": "accepted",
                "compliance": "meets",
            }
        ],
        "proposal_sections": [
            {
                "id": "section",
                "text": "Rated 100 V",
                "requirement_ids": ["req"],
                "evidence_ids": ["evidence"],
                "review_status": "approved",
            }
        ],
    }


@pytest.fixture
def workspace(client, sqlite_engine, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Manual review must never invoke an LLM")

    monkeypatch.setattr("anthropic.Anthropic", forbidden)
    assert (
        client.post(
            "/v2/notices",
            json={
                "notice_no": "COMPLIANCE",
                "title": "Manual compliance",
                "source": "MANUAL",
                "raw": {},
            },
        ).status_code
        == 200
    )
    ws = client.post("/v2/notices/COMPLIANCE/initialize").json()
    ws["inputs"].update(manual_inputs())
    with sqlite_engine.begin() as conn:
        conn.execute(
            update(workspaces)
            .where(workspaces.c.notice_no == "COMPLIANCE")
            .values(
                inputs=ws["inputs"],
                decision="participate",
            )
        )
    return ws


def commercial_payload(**overrides):
    return {
        "version": 1,
        "offer_price": 1000,
        "quantity": 2,
        "document_id": "evidence",
        "quote": "Total KRW 1,000.",
        "locator": "p1",
        "note": "Confirmed total offer",
        **overrides,
    }


@pytest.mark.parametrize("compliance", [None, "unassessed", "does_not_meet", "meets"])
def test_acceptance_is_not_compliance_or_final_readiness(compliance):
    inputs = manual_inputs()
    req = inputs["requirements"][0]
    if compliance is None:
        req.pop("compliance")
    else:
        req["compliance"] = compliance
    docs = {d["id"]: d for d in inputs["documents"]}
    assert requirement_valid(req, docs)
    assert section_valid(inputs["proposal_sections"][0], inputs) == (compliance == "meets")
    assert bool(service.blockers(inputs)) == (compliance != "meets")
    req.update(proposal_disposition="evidence_only", proposal_note="Separate verified document")
    assert proposal_coverage(inputs)["evidence_only_count"] == int(compliance == "meets")


@pytest.mark.parametrize("compliance", ["meets", "does_not_meet", "unassessed"])
def test_manual_compliance_roundtrip_preserves_evidence_acceptance(
    client, sqlite_engine, workspace, compliance
):
    payload = {**workspace["inputs"]["requirements"][0], "version": 1, "compliance": compliance}
    result = client.post("/v2/notices/COMPLIANCE/requirements", json=payload)
    assert result.status_code == 200, result.text
    after = result.json()
    assert after["inputs"]["requirements"][0]["compliance"] == compliance
    assert after["inputs"]["requirements"][0]["review_status"] == "accepted"
    assert after["decision"] == "participate" and after["version"] == 2
    assert after["inputs"]["proposal_sections"][0]["review_status"] == "pending"
    assert after["inputs"]["source_reviewed"] is False
    with sqlite_engine.connect() as conn:
        assert conn.execute(select(budgets)).all() == []
        assert conn.execute(select(jobs)).all() == []


def test_omitted_compliance_defaults_unassessed_in_response(client, workspace):
    payload = {**workspace["inputs"]["requirements"][0], "version": 1}
    payload.pop("compliance")
    response = client.post("/v2/notices/COMPLIANCE/requirements", json=payload)
    assert response.status_code == 200
    assert response.json()["inputs"]["requirements"][0]["compliance"] == "unassessed"


@pytest.mark.parametrize(
    "change",
    [
        {"review_status": "pending"},
        {"quote": "invalid source"},
        {"evidence_id": "source"},
        {"evidence_quote": "invalid evidence"},
        {"category": "schedule", "evidence_id": None},
    ],
)
def test_manual_assessment_still_requires_accepted_source_and_company_evidence(
    client, workspace, change
):
    payload = {**workspace["inputs"]["requirements"][0], "version": 1, **change}
    response = client.post("/v2/notices/COMPLIANCE/requirements", json=payload)
    assert response.status_code == 409
    assert client.get("/v2/notices/COMPLIANCE/workspace").json()["version"] == 1


@pytest.mark.parametrize("compliance", ["unassessed", "does_not_meet"])
def test_proposal_approval_rejects_non_meeting_mandatory_requirement(
    client, sqlite_engine, workspace, compliance
):
    workspace["inputs"]["requirements"][0]["compliance"] = compliance
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=workspace["inputs"]))
    response = client.post(
        "/v2/notices/COMPLIANCE/sections/section/review",
        json={
            "version": 1,
            "text": "Rated 100 V",
            "note": "Review",
            "approved": True,
        },
    )
    assert response.status_code == 409


def test_source_change_invalidates_compliance_but_keeps_history(client, sqlite_engine, workspace):
    response = client.post(
        "/v2/notices/COMPLIANCE/documents/evidence/text",
        json={
            "version": 1,
            "text": "Rated 90 V",
            "note": "Corrected document",
        },
    )
    assert response.status_code == 200
    assert response.json()["inputs"]["requirements"][0]["compliance"] == "unassessed"
    with sqlite_engine.connect() as conn:
        history = (
            conn.execute(select(reviews).where(reviews.c.action == "manual_text")).mappings().one()
        )
    assert history["details"]["previous_inputs"]["requirements"][0]["compliance"] == "meets"


def test_analysis_candidate_cannot_supply_manual_compliance(client, sqlite_engine, workspace):
    result = client.post(
        "/v2/notices/COMPLIANCE/jobs",
        json={
            "kind": "analyze",
            "input_version": 1,
            "idempotency_key": "analysis",
        },
    )
    job_id = result.json()["id"]
    # A different quote too: same document + same quote is a duplicate and is not applied.
    candidate = {**workspace["inputs"]["requirements"][0], "text": "New candidate",
                 "quote": "New candidate quote"}
    with sqlite_engine.begin() as conn:
        conn.execute(
            update(jobs)
            .where(jobs.c.id == job_id)
            .values(
                status="succeeded",
                result={"requirements": [candidate]},
            )
        )
    response = client.post(f"/v2/notices/COMPLIANCE/jobs/{job_id}/apply", json={"version": 1})
    assert response.status_code == 200
    reqs = response.json()["inputs"]["requirements"]
    assert reqs[0]["compliance"] == "meets"
    assert reqs[1]["compliance"] == "unassessed" and reqs[1]["review_status"] == "pending"


def test_commercial_saves_total_and_audits_without_paid_call_or_decision_change(
    client, sqlite_engine, workspace
):
    original = deepcopy(workspace["inputs"])
    response = client.post("/v2/notices/COMPLIANCE/commercial", json=commercial_payload())
    assert response.status_code == 200, response.text
    after = response.json()
    assert after["inputs"]["commercial"] == {
        k: v for k, v in commercial_payload().items() if k != "version"
    }
    assert after["version"] == 2 and after["decision"] == "participate"
    assert after["inputs"]["proposal_sections"][0]["review_status"] == "pending"
    assert after["inputs"]["requirements"] == original["requirements"]
    assert (
        client.post("/v2/notices/COMPLIANCE/commercial", json=commercial_payload()).status_code
        == 409
    )
    with sqlite_engine.connect() as conn:
        history = (
            conn.execute(select(reviews).where(reviews.c.action == "commercial_review"))
            .mappings()
            .one()
        )
        assert history["details"]["previous_inputs"] == original
        assert conn.execute(select(budgets)).all() == []
        assert conn.execute(select(jobs)).all() == []


def test_source_sync_preserves_commercial_and_requires_new_compliance_review(client, workspace):
    saved = client.post("/v2/notices/COMPLIANCE/commercial", json=commercial_payload()).json()
    response = client.post("/v2/notices/COMPLIANCE/sync", json={"version": saved["version"]})
    assert response.status_code == 200, response.text
    after = response.json()
    assert after["inputs"]["commercial"] == saved["inputs"]["commercial"]
    assert after["inputs"]["requirements"][0]["compliance"] == "unassessed"
    assert after["decision"] == "participate"


def test_commercial_revalidated_when_its_evidence_is_changed(client, workspace):
    saved = client.post("/v2/notices/COMPLIANCE/commercial", json=commercial_payload()).json()
    response = client.post("/v2/notices/COMPLIANCE/documents/evidence/text", json={
        "version": saved["version"], "text": "Revised price KRW 2,000", "note": "New quote",
    })
    assert response.status_code == 200, response.text
    after = response.json()
    assert after["inputs"]["commercial"] == saved["inputs"]["commercial"]
    assert any("제안 총액" in issue for issue in after["blockers"])
    assert not after["ready"]


@pytest.mark.parametrize(
    "quote,price,accepted",
    [
        ("KRW 1,000", 1000, True),
        ("1,000원", 1000, True),
        ("₩1000", 1000, True),
        ("Total KRW 1,000.", 1000, True),
        ("KRW 1,000.50", 1000.5, True),
        ("100원", 1, False),
        ("KRW 1,000", 1, False),
        ("KRW 10,00", 1000, False),
        ("$1000", 1000, False),
        ("1000", 1000, False),
        ("USD 1000원", 1000, False),
        ("-1000원", 1000, False),
        ("KRW 1000 million", 1000, False),
        ("KRW 1000 000", 1000, False),
        ("1 1000원", 1000, False),
        ("KRW 1000 %", 1000, False),
        ("\u22121000원", 1000, False),
    ],
)
def test_commercial_exact_total_krw_token(client, sqlite_engine, workspace, quote, price, accepted):
    workspace["inputs"]["documents"][1]["text"] += "\n" + quote
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=workspace["inputs"]))
    response = client.post(
        "/v2/notices/COMPLIANCE/commercial",
        json=commercial_payload(
            quote=quote,
            offer_price=price,
        ),
    )
    assert response.status_code == (200 if accepted else 409), response.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"document_id": "source"},
        {"document_id": "missing"},
        {"quote": "KRW 1001"},
        {"locator": " "},
        {"note": " "},
    ],
)
def test_commercial_requires_actual_confirmed_evidence(client, workspace, overrides):
    assert (
        client.post(
            "/v2/notices/COMPLIANCE/commercial", json=commercial_payload(**overrides)
        ).status_code
        == 409
    )


def test_unconfirmed_commercial_evidence_rejected(client, sqlite_engine, workspace):
    workspace["inputs"]["documents"][1]["confirmed"] = False
    with sqlite_engine.begin() as conn:
        conn.execute(update(workspaces).values(inputs=workspace["inputs"]))
    assert (
        client.post("/v2/notices/COMPLIANCE/commercial", json=commercial_payload()).status_code
        == 409
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"offer_price": 0},
        {"offer_price": -1},
        {"offer_price": True},
        {"offer_price": float("inf")},
        {"offer_price": float("nan")},
        {"quantity": 0},
        {"quantity": -1},
        {"quantity": 1.5},
        {"quantity": True},
        {"quantity": "2"},
    ],
)
def test_commercial_request_rejects_invalid_numbers(overrides):
    with pytest.raises(ValidationError):
        CommercialRequest(**commercial_payload(**overrides))
