"""POST/GET/DELETE /notices/{notice_no}/documents/uploads* 통합 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select
from sqlalchemy.pool import StaticPool

from api.config import settings
from api.main import app
from api.routers.notices import bid_pipeline, metadata


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
    monkeypatch.setattr(settings, "upload_allowed_exts", "pdf,hwp,jpg,xlsx")
    return engine


@pytest.fixture
def client(sqlite_engine, monkeypatch):
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    return TestClient(app)


def _seed_with_document_automation(engine):
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no="DOC-1",
                title="ABB 변압기",
                source="G2B",
                raw={},
                category="ABB장비",
                fit_score=80,
                assignee="이용문",
                analysis={
                    "document_automation": {
                        "checklist": [
                            {"id": "business_registration", "name": "사업자등록증",
                             "type": "company_common", "required": True,
                             "status": "needed", "source": "rule",
                             "owner": None, "reason": None, "due_hint": None, "note": None},
                            {"id": "bid_form", "name": "입찰참가신청서",
                             "type": "bid_form", "required": True,
                             "status": "needed", "source": "rule",
                             "owner": None, "reason": None, "due_hint": None, "note": None},
                        ],
                        "drafts": {},
                        "risks": [],
                        "generated_at": now.isoformat(),
                        "source": "rule",
                        "ready_for_submission": False,
                        "missing_required": [],
                        "errors": [],
                        "uploads": [],
                        "exports": [],
                    }
                },
                status="analyzed",
                created_at=now,
                updated_at=now,
            )
        )


def test_upload_404_when_notice_missing(client):
    r = client.post(
        "/notices/MISSING/documents/uploads",
        files={"file": ("a.pdf", b"x", "application/pdf")},
    )
    assert r.status_code == 404


def test_upload_409_when_document_automation_missing(client, sqlite_engine):
    now = datetime.now(tz=UTC)
    with sqlite_engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no="DOC-1",
                title="t",
                source="G2B",
                raw={},
                category="ABB장비",
                fit_score=0,
                assignee="x",
                analysis={},
                status="analyzed",
                created_at=now,
                updated_at=now,
            )
        )
    r = client.post(
        "/notices/DOC-1/documents/uploads",
        files={"file": ("a.pdf", b"x", "application/pdf")},
    )
    assert r.status_code == 409


def test_upload_rejects_disallowed_extension(client, sqlite_engine):
    _seed_with_document_automation(sqlite_engine)
    r = client.post(
        "/notices/DOC-1/documents/uploads",
        files={"file": ("a.exe", b"x", "application/x-msdownload")},
    )
    assert r.status_code == 415


def test_upload_creates_metadata_and_promotes_item(client, sqlite_engine):
    _seed_with_document_automation(sqlite_engine)
    r = client.post(
        "/notices/DOC-1/documents/uploads",
        files={"file": ("biz.pdf", b"hello", "application/pdf")},
        data={"item_id": "business_registration"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uploaded"]["name"] == "biz.pdf"
    assert body["uploaded"]["item_id"] == "business_registration"
    assert body["uploaded"]["size"] == 5

    # 체크리스트 항목이 ready로 승격
    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "DOC-1")
        ).mappings().one()
    docs = row["analysis"]["document_automation"]
    bizn = next(i for i in docs["checklist"] if i["id"] == "business_registration")
    assert bizn["status"] == "ready"
    assert "upload" in bizn["source"]


def test_pdf_upload_auto_detects_and_promotes_item(client, sqlite_engine, monkeypatch):
    _seed_with_document_automation(sqlite_engine)
    monkeypatch.setattr(
        "api.services.uploads.extract_pdf_text",
        lambda _b: "사업자등록증 사업자등록번호 회사명",
    )
    r = client.post(
        "/notices/DOC-1/documents/uploads",
        files={"file": ("company.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 200, r.text
    uploaded = r.json()["uploaded"]
    assert uploaded["detected_item_id"] == "business_registration"
    assert uploaded["item_id"] == "business_registration"
    assert uploaded["detect_confidence"] >= 0.75
    assert "사업자등록증" in uploaded["analysis_summary"]

    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "DOC-1")
        ).mappings().one()
    docs = row["analysis"]["document_automation"]
    bizn = next(i for i in docs["checklist"] if i["id"] == "business_registration")
    assert bizn["status"] == "ready"


def test_explicit_item_id_wins_over_auto_detection(client, sqlite_engine, monkeypatch):
    _seed_with_document_automation(sqlite_engine)
    monkeypatch.setattr(
        "api.services.uploads.extract_pdf_text",
        lambda _b: "사업자등록증 사업자등록번호 회사명",
    )
    r = client.post(
        "/notices/DOC-1/documents/uploads",
        files={"file": ("company.pdf", b"%PDF", "application/pdf")},
        data={"item_id": "bid_form"},
    )
    assert r.status_code == 200, r.text
    uploaded = r.json()["uploaded"]
    assert uploaded["detected_item_id"] == "business_registration"
    assert uploaded["item_id"] == "bid_form"


def test_hwp_agent_failure_records_error_but_upload_succeeds(client, sqlite_engine, monkeypatch):
    _seed_with_document_automation(sqlite_engine)

    class FailingClient:
        def analyze_document(self, _path):
            from api.services.hwp_agent_client import HwpAgentError

            raise HwpAgentError("agent down")

    monkeypatch.setattr("api.routers.notices._common._make_hwp_agent_client", lambda: FailingClient())
    r = client.post(
        "/notices/DOC-1/documents/uploads",
        files={"file": ("form.hwp", b"HWP", "application/x-hwp")},
    )
    assert r.status_code == 200, r.text
    uploaded = r.json()["uploaded"]
    assert uploaded["text_extract_error"]
    assert "agent down" in uploaded["text_extract_error"]


def test_common_upload_import_promotes_current_notice_item(client, sqlite_engine, monkeypatch):
    _seed_with_document_automation(sqlite_engine)
    monkeypatch.setattr(
        "api.services.uploads.extract_pdf_text",
        lambda _b: "사업자등록증 사업자등록번호 회사명",
    )
    common = client.post(
        "/documents/common/uploads",
        files={"file": ("common-biz.pdf", b"%PDF", "application/pdf")},
    )
    assert common.status_code == 200, common.text
    upload_id = common.json()["uploaded"]["id"]

    r = client.post(f"/notices/DOC-1/documents/import-common/{upload_id}")
    assert r.status_code == 200, r.text
    imported = r.json()["uploaded"]
    assert imported["source_ref"] == "common_library"
    assert imported["item_id"] == "business_registration"

    with sqlite_engine.begin() as conn:
        row = conn.execute(
            select(bid_pipeline.c.analysis).where(bid_pipeline.c.notice_no == "DOC-1")
        ).mappings().one()
    docs = row["analysis"]["document_automation"]
    bizn = next(i for i in docs["checklist"] if i["id"] == "business_registration")
    assert bizn["status"] == "ready"


def test_list_uploads_returns_persisted_items(client, sqlite_engine):
    _seed_with_document_automation(sqlite_engine)
    client.post(
        "/notices/DOC-1/documents/uploads",
        files={"file": ("a.pdf", b"a", "application/pdf")},
    )
    client.post(
        "/notices/DOC-1/documents/uploads",
        files={"file": ("b.pdf", b"b", "application/pdf")},
    )
    r = client.get("/notices/DOC-1/documents/uploads")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {i["name"] for i in items} == {"a.pdf", "b.pdf"}


def test_delete_upload_removes_meta_and_disk_file(client, sqlite_engine, tmp_path):
    _seed_with_document_automation(sqlite_engine)
    up = client.post(
        "/notices/DOC-1/documents/uploads",
        files={"file": ("a.pdf", b"a", "application/pdf")},
    ).json()
    upload_id = up["uploaded"]["id"]
    storage_path = up["uploaded"]["storage_path"]

    import os
    assert os.path.isfile(storage_path)

    r = client.delete(f"/notices/DOC-1/documents/uploads/{upload_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] == upload_id
    assert not os.path.isfile(storage_path)

    r2 = client.get("/notices/DOC-1/documents/uploads")
    assert r2.json()["items"] == []


def test_delete_unknown_upload_returns_404(client, sqlite_engine):
    _seed_with_document_automation(sqlite_engine)
    r = client.delete("/notices/DOC-1/documents/uploads/nonexistent-id")
    assert r.status_code == 404


def test_download_upload_streams_file(client, sqlite_engine):
    _seed_with_document_automation(sqlite_engine)
    up = client.post(
        "/notices/DOC-1/documents/uploads",
        files={"file": ("a.pdf", b"hello-bid", "application/pdf")},
    ).json()
    upload_id = up["uploaded"]["id"]
    r = client.get(f"/notices/DOC-1/documents/uploads/{upload_id}/download")
    assert r.status_code == 200
    assert r.content == b"hello-bid"
    assert r.headers["content-type"].startswith("application/pdf")
