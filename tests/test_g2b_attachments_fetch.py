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


def test_fetch_retries_failed_upload_and_resolves_prior_error(
    client,
    sqlite_engine,
    monkeypatch,
):
    """에이전트/추출 복구 후 재실행하면 이전 실패를 재처리하고 묵은 오류를 해소한다."""
    _seed_notice(
        sqlite_engine,
        raw={"ntceSpecDocUrl1": PDF_DATA_URL, "ntceSpecFileNm1": "spec.pdf"},
    )

    def _boom(_b):
        raise RuntimeError("pdf parse boom")

    monkeypatch.setattr("api.services.uploads.extract_pdf_text", _boom)
    first = client.post("/notices/ATT-1/attachments/fetch")
    assert first.status_code == 200
    assert first.json()["status"] == "completed_with_errors"
    with sqlite_engine.begin() as conn:
        unresolved = conn.execute(
            select(notice_errors).where(
                notice_errors.c.notice_no == "ATT-1",
                notice_errors.c.resolved_at.is_(None),
            )
        ).mappings().all()
    assert len(unresolved) >= 1

    # 복구: 추출 성공 → 재실행은 skip이 아니라 재처리(success) + 묵은 오류 resolved.
    monkeypatch.setattr(
        "api.services.uploads.extract_pdf_text", lambda _b: "규격 사양 spec ok"
    )
    second = client.post("/notices/ATT-1/attachments/fetch")
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["status"] == "completed"
    assert body["errors"] == []
    assert body["files"][0]["status"] == "success"
    with sqlite_engine.begin() as conn:
        unresolved = conn.execute(
            select(notice_errors).where(
                notice_errors.c.notice_no == "ATT-1",
                notice_errors.c.resolved_at.is_(None),
            )
        ).mappings().all()
        row = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "ATT-1")
        ).mappings().one()
    assert unresolved == []
    uploads = row["analysis"]["document_automation"]["uploads"]
    assert len(uploads) == 1
    assert not uploads[0].get("text_extract_error")


def test_fetch_reevaluates_checklist_from_attachment_text(client, sqlite_engine, monkeypatch):
    """첨부 fetch 후 자동 재평가: 받은 첨부 본문 근거로 체크리스트 required가 갱신된다."""
    _seed_notice(
        sqlite_engine,
        raw={"ntceSpecDocUrl1": PDF_DATA_URL, "ntceSpecFileNm1": "공고서.pdf"},
    )
    # 분석 전 초기 상태: 보증 키워드가 메타데이터에 없어 bid_bond는 해당없음/선택.
    monkeypatch.setattr(
        "api.services.uploads.extract_pdf_text",
        lambda _b: "본 입찰은 입찰보증금 납부 조건이 적용됩니다.",
    )

    r = client.post("/notices/ATT-1/attachments/fetch")
    assert r.status_code == 200, r.text

    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "ATT-1")
        ).mappings().one()
    by_id = {i["id"]: i for i in row["analysis"]["document_automation"]["checklist"]}
    # 첨부 본문에 "입찰보증금"이 있으므로 재평가 후 bid_bond가 필요(required=True)로 승격.
    assert by_id["bid_bond"]["required"] is True


def test_fetch_resets_stale_attachment_errors_but_preserves_other_stages(
    client,
    sqlite_engine,
    monkeypatch,
):
    """UI가 읽는 document_automation['errors']는 재실행 시 attachment 단계만 교체하고
    다른 단계(autofill 등) 오류는 보존해야 한다(과거 실패 무한 누적 방지)."""
    stale = [
        {"stage": "g2b_attachment_analysis", "severity": "warning", "detail": "old hwp fail"},
        {"stage": "g2b_attachment_fetch", "detail": "old write fail"},
        {"stage": "autofill_form", "detail": "keep me"},
    ]
    _seed_notice(
        sqlite_engine,
        raw={"ntceSpecDocUrl1": PDF_DATA_URL, "ntceSpecFileNm1": "spec.pdf"},
        analysis={"document_automation": {"checklist": [], "uploads": [], "errors": stale}},
    )
    monkeypatch.setattr("api.services.uploads.extract_pdf_text", lambda _b: "규격 사양 ok")

    resp = client.post("/notices/ATT-1/attachments/fetch")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"

    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "ATT-1")
        ).mappings().one()
    stages = [e["stage"] for e in row["analysis"]["document_automation"]["errors"]]
    assert stages == ["autofill_form"]


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
