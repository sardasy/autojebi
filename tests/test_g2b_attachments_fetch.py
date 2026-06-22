from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select
from sqlalchemy.pool import StaticPool

from api.config import settings
from api.main import app
from api.routers.notices import (
    attachment_fetch_files,
    attachment_fetch_jobs,
    bid_pipeline,
    metadata,
    notice_errors,
)

PDF_DATA_URL = "data:application/pdf;base64,JVBERi0xLjQKJUVPRgo="


@pytest.fixture
def sqlite_engine(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    monkeypatch.setattr("api.db.get_engine", lambda: engine)
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "upload_max_bytes", 10_000)
    monkeypatch.setattr(settings, "upload_allowed_exts", "pdf,hwp,hwpx,jpg,xlsx")
    return engine


@pytest.fixture
def client(sqlite_engine, monkeypatch):
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    return TestClient(app)


def _seed_notice(engine, raw: dict | None = None, analysis: dict | None = None) -> None:
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no="ATT-1",
                title="ABB 변압기 시험기",
                source="G2B",
                raw=raw or {},
                category="ABB장비",
                fit_score=80,
                assignee="이용문",
                analysis=analysis or {},
                status="analyzed",
                created_at=now,
                updated_at=now,
            )
        )


def test_fetch_g2b_attachment_downloads_analyzes_and_merges_upload(
    client,
    sqlite_engine,
    monkeypatch,
):
    _seed_notice(
        sqlite_engine,
        raw={
            "ntceSpecDocUrl1": PDF_DATA_URL,
            "ntceSpecFileNm1": "사업자등록증.pdf",
        },
    )
    monkeypatch.setattr(
        "api.services.uploads.extract_pdf_text",
        lambda _b: "사업자등록증 사업자등록번호 회사명",
    )

    response = client.post("/notices/ATT-1/attachments/fetch")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"]
    assert body["status"] == "completed"
    assert body["files"][0]["status"] == "success"
    assert body["errors"] == []
    assert len(body["fetched"]) == 1
    uploaded = body["fetched"][0]
    assert uploaded["name"] == "사업자등록증.pdf"
    assert uploaded["source_ref"] == "g2b_attachment"
    assert uploaded["item_id"] == "business_registration"
    assert uploaded["analysis_summary"]

    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "ATT-1")
        ).mappings().one()
        job = conn.execute(select(attachment_fetch_jobs)).mappings().one()
        file_result = conn.execute(select(attachment_fetch_files)).mappings().one()
    docs = row["analysis"]["document_automation"]
    assert len(docs["uploads"]) == 1
    assert docs["uploads"][0]["source_ref"] == "g2b_attachment"
    business_registration = next(
        item for item in docs["checklist"] if item["id"] == "business_registration"
    )
    assert business_registration["status"] == "ready"
    assert job["status"] == "completed"
    assert file_result["status"] == "success"
    assert file_result["upload_id"] == uploaded["id"]


def test_fetch_g2b_attachment_is_idempotent(client, sqlite_engine, monkeypatch):
    _seed_notice(
        sqlite_engine,
        raw={
            "ntceSpecDocUrl1": PDF_DATA_URL,
            "ntceSpecFileNm1": "spec.pdf",
        },
    )
    monkeypatch.setattr("api.services.uploads.extract_pdf_text", lambda _b: "규격 사양 spec")

    first = client.post("/notices/ATT-1/attachments/fetch")
    second = client.post("/notices/ATT-1/attachments/fetch")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["files"][0]["status"] == "skipped"
    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "ATT-1")
        ).mappings().one()
    uploads = row["analysis"]["document_automation"]["uploads"]
    assert len(uploads) == 1
    assert second.json()["fetched"][0]["id"] == uploads[0]["id"]


def test_fetch_g2b_attachment_records_file_error_without_failing_notice(
    client,
    sqlite_engine,
):
    _seed_notice(
        sqlite_engine,
        raw={
            "ntceSpecDocUrl1": "data:application/pdf;base64,not-valid",
            "ntceSpecFileNm1": "bad.pdf",
        },
    )

    response = client.post("/notices/ATT-1/attachments/fetch")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed_with_errors"
    assert body["files"][0]["status"] == "failed"
    assert body["fetched"] == []
    assert body["errors"][0]["file_name"] == "bad.pdf"
    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c.analysis, bid_pipeline.c.status).where(
                bid_pipeline.c.notice_no == "ATT-1"
            )
        ).mappings().one()
    docs = row["analysis"]["document_automation"]
    assert docs["uploads"] == []
    assert docs["errors"][0]["stage"] == "g2b_attachment_fetch"
    assert row["status"] == "attachments_fetched"
    with sqlite_engine.begin() as conn:
        error = conn.execute(select(notice_errors).where(notice_errors.c.notice_no == "ATT-1")).mappings().one()
    assert error["stage"] == "g2b_attachment_fetch"
    assert error["file_name"] == "bad.pdf"


def test_fetch_g2b_attachment_records_mixed_file_results(client, sqlite_engine, monkeypatch):
    _seed_notice(
        sqlite_engine,
        raw={
            "ntceSpecDocUrl1": PDF_DATA_URL,
            "ntceSpecFileNm1": "good.pdf",
            "ntceSpecDocUrl2": "data:application/pdf;base64,not-valid",
            "ntceSpecFileNm2": "bad.pdf",
        },
    )
    monkeypatch.setattr("api.services.uploads.extract_pdf_text", lambda _b: "규격 사양 spec")

    response = client.post("/notices/ATT-1/attachments/fetch")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed_with_errors"
    assert len(body["fetched"]) == 1
    assert [item["status"] for item in body["files"]] == ["success", "failed"]
    with sqlite_engine.begin() as conn:
        jobs = conn.execute(select(attachment_fetch_jobs.c.status)).scalars().all()
        files = conn.execute(
            select(attachment_fetch_files.c.filename, attachment_fetch_files.c.status)
            .order_by(attachment_fetch_files.c.id)
        ).all()
    assert jobs == ["completed_with_errors"]
    assert files == [("good.pdf", "success"), ("bad.pdf", "failed")]
