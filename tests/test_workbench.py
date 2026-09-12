from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import insert, select, update

from api.models.notices import UploadedDocument
from api.routers.notices import bid_pipeline, hwp_generation_jobs, notice_spec_items
from api.services.uploads import merge_into_document_automation, remove_from_document_automation


def seed(engine):
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no="UX-1",
                title="작업대 공고",
                source="test",
                raw={},
                status="analyzed",
                category="ABB장비",
                fit_score=80,
                assignee="",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                analysis={"document_automation": {"checklist": [], "drafts": {}, "errors": []}},
            )
        )


def test_list_detail_share_spec_counts(client, sqlite_engine):
    seed(sqlite_engine)
    with sqlite_engine.begin() as conn:
        for index, value in enumerate(["220V", "", " "]):
            conn.execute(
                insert(notice_spec_items).values(
                    notice_no="UX-1",
                    item_key=f"spec-{index}",
                    label="전압",
                    required_value=value,
                    category="technical",
                    source="test",
                    evidence={},
                    status="candidate",
                )
            )
    detail = client.get("/notices/UX-1").json()
    listing = client.get("/notices", params={"q": "UX-1", "lifecycle": "all"}).json()["items"][0]
    assert detail["spec_item_count"] == listing["spec_item_count"] == 3
    assert detail["spec_value_count"] == listing["spec_value_count"] == 1


def test_failed_job_cannot_be_approved_and_list_filters(client, sqlite_engine):
    seed(sqlite_engine)
    with sqlite_engine.begin() as conn:
        for status in ["failed", "pending"]:
            conn.execute(
                insert(hwp_generation_jobs).values(
                    notice_no="UX-1",
                    status=status,
                    context_json={},
                    input_values={},
                    replaced=[],
                    missing=["address"],
                    remaining_placeholders=[],
                    worker_raw={},
                    review_status="pending",
                    created_at=datetime.now(UTC),
                )
            )
    result = client.get(
        "/documents/hwp-jobs",
        params={"q": "작업대", "status": "failed", "review_status": "pending", "page_size": 1},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["title"] == "작업대 공고"
    assert item["export"] is None
    assert item["job"]["created_at"]
    job_id = item["job"]["id"]
    url = f"/notices/UX-1/documents/hwp-jobs/{job_id}/review"
    assert (
        client.post(url, json={"review_status": "approved", "review_note": "확인"}).status_code
        == 409
    )
    with sqlite_engine.begin() as conn:
        assert (
            conn.execute(
                select(hwp_generation_jobs.c.review_status).where(
                    hwp_generation_jobs.c.id == job_id
                )
            ).scalar_one()
            == "pending"
        )
    assert (
        client.post(
            url, json={"review_status": "rejected", "review_note": "재생성 필요"}
        ).status_code
        == 200
    )
    assert (
        client.get("/documents/hwp-jobs", params={"review_status": "rejected"}).json()["total"] == 1
    )
    assert client.get("/documents/hwp-jobs", params={"status": "bogus"}).status_code == 422
    assert client.get("/documents/hwp-jobs", params={"page": 0}).status_code == 422
    assert client.get("/documents/hwp-jobs", params={"page": 9}).json()["items"] == []


def test_upload_and_last_removal_recalculate_readiness():
    docs = {
        "checklist": [
            {
                "id": "registration",
                "name": "등록증",
                "type": "company_common",
                "required": True,
                "status": "needed",
                "source": "rule",
            }
        ],
        "drafts": {},
        "uploads": [],
    }
    upload = UploadedDocument(
        id="one",
        name="sample.pdf",
        storage_path="sample.pdf",
        size=3,
        uploaded_at=datetime.now(UTC).isoformat(),
        item_id="registration",
    )
    updated = merge_into_document_automation(docs, upload)
    assert len(updated["missing_required"]) == 1
    assert updated["ready_for_submission"] is False
    assert docs["checklist"][0]["status"] == "needed"
    updated = merge_into_document_automation(updated, upload.model_copy(update={"id": "two"}))
    updated, _ = remove_from_document_automation(updated, "one")
    assert updated["ready_for_submission"] is False
    updated, _ = remove_from_document_automation(updated, "two")
    assert updated["ready_for_submission"] is False
    assert len(updated["missing_required"]) == 1


@pytest.mark.parametrize(
    "failure,fragment",
    [
        (ValueError("G2B_KEY_MISSING"), "키가 설정"),
        (PermissionError("G2B_AUTH_FAILED"), "인증"),
        (httpx.ReadTimeout("secret URL"), "시간"),
        (httpx.ConnectTimeout("secret URL"), "방화벽"),
        (httpx.ConnectError("secret URL"), "DNS"),
        (ValueError("G2B_RATE_LIMITED"), "허용량"),
        (ValueError("G2B_IP_BLOCKED"), "IP"),
        (ValueError("G2B_UPSTREAM_TIMEOUT"), "중계"),
        (ValueError("secret URL"), "외부"),
    ],
)
def test_g2b_failures_have_distinct_safe_messages(client, monkeypatch, failure, fragment):
    from api.collector.g2b_client import G2BClient

    async def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(G2BClient, "search_single", fail)
    response = client.post("/notices/search", json={"keyword": "변압기"})
    assert response.status_code == 502
    assert fragment in response.json()["detail"]
    assert "secret" not in response.text


def test_saved_sections_and_company_profile_read_only(client, sqlite_engine, monkeypatch):
    seed(sqlite_engine)
    monkeypatch.setenv("COMPANY_NAME", "테스트회사")
    assert client.get("/documents/company-profile").json()["company_name"] == "테스트회사"
    assert client.get("/proposals/UX-1/sections").json()["sections"] == []
    assert client.get("/proposals/missing/sections").status_code == 404


def test_summary_uses_current_checklist_not_stale_ready_flag(client, sqlite_engine):
    seed(sqlite_engine)
    docs = {
        "checklist": [
            {
                "id": "registration",
                "name": "등록증",
                "type": "company_common",
                "required": True,
                "status": "needed",
                "source": "rule",
            }
        ],
        "ready_for_submission": True,
        "drafts": {},
        "errors": [{"stage": "hwp", "detail": "old failure"}],
    }
    with sqlite_engine.begin() as conn:
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == "UX-1")
            .values(analysis={"document_automation": docs})
        )
    summary = client.get("/notices/summary").json()
    assert summary["blocked_documents"] == 1
    assert summary["ready_for_submission"] == 0
    docs["checklist"][0]["status"] = "ready"
    docs["ready_for_submission"] = False
    with sqlite_engine.begin() as conn:
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == "UX-1")
            .values(analysis={"document_automation": docs})
        )
    summary = client.get("/notices/summary").json()
    assert summary["blocked_documents"] == 0
    assert summary["ready_for_submission"] == 1
