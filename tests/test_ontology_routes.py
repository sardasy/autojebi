"""M14 — 온톨로지 읽기 API 통합 테스트."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.config import settings
from api.main import app
from api.ontology.seed import seed_ontology
from api.ontology.tables import ontology_concepts

# sqlite_engine, client fixture는 tests/conftest.py에서 제공


@pytest.fixture
def seeded_engine(sqlite_engine):
    seed_ontology(sqlite_engine)
    return sqlite_engine


def _concept_id(engine, canonical_key: str) -> int:
    with engine.begin() as conn:
        return conn.execute(
            select(ontology_concepts.c.id).where(
                ontology_concepts.c.canonical_key == canonical_key
            )
        ).scalar_one()


def test_list_concepts_filters_by_kind(client, seeded_engine):
    r = client.get("/ontology/concepts", params={"kind": "document_type"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 9
    assert all(it["kind"] == "document_type" for it in body["items"])


def test_get_concept_by_canonical_key_200(client, seeded_engine):
    r = client.get("/ontology/concepts/product_category:hil")
    assert r.status_code == 200
    body = r.json()
    assert body["display_name_ko"] == "HIL"
    assert body["kind"] == "product_category"


def test_get_concept_by_canonical_key_404(client, seeded_engine):
    r = client.get("/ontology/concepts/missing:foo")
    assert r.status_code == 404


def test_list_concepts_pagination(client, seeded_engine):
    r = client.get("/ontology/concepts", params={"page": 1, "page_size": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 25
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert body["total_pages"] == 3
    assert len(body["items"]) == 10

    # 마지막 페이지
    r = client.get("/ontology/concepts", params={"page": 3, "page_size": 10})
    body = r.json()
    assert len(body["items"]) == 5
    assert body["page"] == 3


def test_list_concepts_rejects_invalid_pagination(client, seeded_engine):
    r = client.get("/ontology/concepts", params={"page": 0})
    assert r.status_code == 422
    r = client.get("/ontology/concepts", params={"page_size": 0})
    assert r.status_code == 422
    r = client.get("/ontology/concepts", params={"page_size": 999})
    assert r.status_code == 422


def test_list_concepts_search_filter(client, seeded_engine):
    """`?q=HIL`로 product_category:hil 1건을 찾는다."""
    r = client.get("/ontology/concepts", params={"q": "HIL"})
    assert r.status_code == 200
    keys = {it["canonical_key"] for it in r.json()["items"]}
    assert "product_category:hil" in keys


def test_aliases_requires_concept_id(client, seeded_engine):
    r = client.get("/ontology/aliases")
    assert r.status_code == 422


def test_list_aliases_for_hil(client, seeded_engine):
    cid = _concept_id(seeded_engine, "product_category:hil")
    r = client.get("/ontology/aliases", params={"concept_id": cid})
    assert r.status_code == 200
    alias_texts = {a["alias_text"] for a in r.json()}
    assert "Hardware-in-the-Loop" in alias_texts
    assert "Typhoon HIL" in alias_texts


def test_relations_requires_at_least_one_filter(client, seeded_engine):
    r = client.get("/ontology/relations")
    assert r.status_code == 422
    assert "at least one filter" in r.json()["detail"].lower()


def test_role_bindings_match_routing(client, seeded_engine):
    tech_sw = _concept_id(seeded_engine, "role:tech_sw")
    r = client.get("/ontology/role-bindings", params={"role_concept_id": tech_sw})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["assignee"] == "Sangjun"


def test_notice_assertions_empty_when_no_data(client, seeded_engine):
    r = client.get("/ontology/notices/UNKNOWN-001/assertions")
    assert r.status_code == 200
    assert r.json() == []


def test_notice_work_tasks_empty_when_no_data(client, seeded_engine):
    r = client.get("/ontology/notices/UNKNOWN-001/work-tasks")
    assert r.status_code == 200
    assert r.json() == []


def test_auth_blocks_when_api_key_set(sqlite_engine, monkeypatch):
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    monkeypatch.setattr(settings, "api_key", "secret-key-123")
    seed_ontology(sqlite_engine)
    c = TestClient(app)
    r = c.get("/ontology/concepts")
    assert r.status_code in (401, 403)

    r = c.get(
        "/ontology/concepts",
        headers={"X-API-Key": "secret-key-123"},
    )
    assert r.status_code == 200


def test_list_rules_empty_default(client, seeded_engine):
    r = client.get("/ontology/rules")
    assert r.status_code == 200
    assert r.json() == []


def test_list_rules_filter_by_active(client, seeded_engine):
    """active=true/false 필터 (현재 데이터 없음 — 빈 응답 두 케이스 모두 정상)."""
    r = client.get("/ontology/rules", params={"active": "true"})
    assert r.status_code == 200
    assert r.json() == []

    r = client.get("/ontology/rules", params={"active": "false"})
    assert r.status_code == 200
    assert r.json() == []


def test_get_evidence_404(client, seeded_engine):
    r = client.get("/ontology/evidence/999999")
    assert r.status_code == 404
    assert "999999" in r.json()["detail"]


def test_list_role_bindings_filter_by_assignee(client, seeded_engine):
    """`?assignee=Sangjun` → tech_sw 매핑 1건만 반환."""
    r = client.get("/ontology/role-bindings", params={"assignee": "Sangjun"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["assignee"] == "Sangjun"


def test_list_role_bindings_active_at(client, seeded_engine):
    """시드된 binding은 valid_from=NOW(), valid_to=None이므로 "현재"는 모두 활성."""
    from datetime import datetime, timezone

    now_iso = datetime.now(tz=timezone.utc).isoformat()
    r = client.get("/ontology/role-bindings", params={"active_at": now_iso})
    assert r.status_code == 200
    body = r.json()
    # 시드 3건 모두 활성 (Sangjun / 이용문 / 미배정)
    assert len(body) == 3
