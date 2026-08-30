from __future__ import annotations

from sqlalchemy import insert, select

from api.routers.notices import (
    bid_pipeline,
    notice_requirements,
    proposal_sections,
    requirement_evidences,
)


def _seed_notice(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no="PROP-1",
                title="HIL 실시간 시뮬레이션 구축 제안 요청",
                source="G2B",
                raw={
                    "ntceInsttNm": "OO대학교",
                    "bidNtceNm": "HIL 실시간 시뮬레이션 구축",
                    "cntrctCnclsMthdNm": "협상에 의한 계약",
                },
                category="Typhoon HIL",
                fit_score=88,
                analysis={
                    "document_automation": {
                        "checklist": [
                            {
                                "id": "proposal",
                                "name": "제안서",
                                "type": "technical",
                                "required": True,
                                "status": "needed",
                                "reason": "유사실적 및 기술지원 계획 필요",
                                "source": "rule",
                            }
                        ],
                        "drafts": {},
                        "risks": [],
                        "generated_at": "2026-08-30T00:00:00Z",
                        "source": "test",
                        "ready_for_submission": False,
                        "missing_required": [],
                        "errors": [],
                        "uploads": [],
                        "exports": [],
                    }
                },
                status="analyzed",
            )
        )


def test_proposal_agent_workspace_flow(client, sqlite_engine):
    _seed_notice(sqlite_engine)

    doc = client.post(
        "/proposals/documents",
        json={
            "title": "2025 OO대학교 HIL 구축 제안서",
            "category": "proposal",
            "project_name": "HIL 구축",
            "customer_name": "OO대학교",
            "document_metadata": {
                "product": ["HIL606"],
                "technology": ["HIL", "실시간 시뮬레이션"],
            },
            "chunks": [
                {
                    "chunk_index": 0,
                    "page_number": 21,
                    "heading": "유사 사업 수행실적",
                    "content": "Typhoon HIL606 기반 전력전자 실시간 시뮬레이션 환경을 구축하고 기술지원과 교육을 수행했습니다.",
                }
            ],
        },
    )
    assert doc.status_code == 200
    assert doc.json()["indexing_status"] == "indexed"

    perf = client.post(
        "/proposals/performances",
        json={
            "project_name": "전력변환 HIL 시험환경 구축",
            "customer_name": "OO대학교",
            "contract_amount": 68000000,
            "project_type": "HIL 구축",
            "technologies": ["HIL", "Typhoon HIL"],
            "products": ["HIL606"],
            "description": "대학 연구기관 대상 실시간 시뮬레이션 납품 및 기술지원",
            "evidence_document_id": doc.json()["id"],
            "verified": True,
        },
    )
    assert perf.status_code == 200
    assert perf.json()["verified"] is True

    analyzed = client.post("/proposals/analyze/PROP-1")
    assert analyzed.status_code == 200
    req_types = {item["requirement_type"] for item in analyzed.json()["requirements"]}
    assert "similar_experience" in req_types
    assert "technical_strength" in req_types

    retrieved = client.post("/proposals/PROP-1/retrieve")
    assert retrieved.status_code == 200
    assert len(retrieved.json()["evidences"]) >= 2
    assert any(item["evidence_type"] == "performance" for item in retrieved.json()["evidences"])

    generated = client.post("/proposals/PROP-1/generate")
    assert generated.status_code == 200
    assert any("Evidence:" in item["generated_content"] for item in generated.json()["sections"])

    verified = client.post("/proposals/PROP-1/verify")
    assert verified.status_code == 200
    assert verified.json()["status"] in {"pass", "warning"}

    coverage = client.get("/proposals/PROP-1/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["readiness_score"] > 0

    with sqlite_engine.begin() as conn:
        assert conn.execute(select(notice_requirements.c.id)).first() is not None
        assert conn.execute(select(requirement_evidences.c.id)).first() is not None
        assert conn.execute(select(proposal_sections.c.id)).first() is not None


def test_proposal_retrieve_requires_analyze_first(client, sqlite_engine):
    _seed_notice(sqlite_engine)
    response = client.post("/proposals/PROP-1/retrieve")
    assert response.status_code == 409
    assert response.json()["detail"] == "run proposal analyze first"
