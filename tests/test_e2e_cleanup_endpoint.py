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
    notice_exports,
    notice_spec_items,
)


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
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    monkeypatch.setattr(settings, "e2e_cleanup_enabled", False)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    return engine


@pytest.fixture
def client(sqlite_engine):
    return TestClient(app)


def _insert_notice(engine, notice_no: str, analysis: dict | None = None) -> None:
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no=notice_no,
                title=f"{notice_no} title",
                source="E2E",
                raw={},
                category="혼합",
                fit_score=0,
                assignee="x",
                analysis=analysis or {},
                status="analyzed",
                created_at=now,
                updated_at=now,
            )
        )


def test_e2e_cleanup_disabled_by_default(client, sqlite_engine):
    _insert_notice(sqlite_engine, "E2E-KEEP-1")

    response = client.post("/notices/e2e/cleanup")

    assert response.status_code == 403
    with sqlite_engine.begin() as conn:
        assert conn.execute(select(bid_pipeline.c.notice_no)).scalar_one() == "E2E-KEEP-1"


def test_e2e_cleanup_deletes_only_e2e_rows_and_runtime_files(
    client,
    sqlite_engine,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "e2e_cleanup_enabled", True)
    upload_path = tmp_path / "upload.pdf"
    export_path = tmp_path / "export.xlsx"
    common_path = tmp_path / "common.pdf"
    for path in (upload_path, export_path, common_path):
        path.write_bytes(b"x")

    _insert_notice(
        sqlite_engine,
        "E2E-CLEAN-1",
        {
            "document_automation": {
                "uploads": [
                    {"id": "u1", "storage_path": str(upload_path), "source_ref": "uploaded"},
                    {
                        "id": "u2",
                        "storage_path": str(common_path),
                        "source_ref": "common_library",
                    },
                ],
                "exports": [{"kind": "excel", "output_path": str(export_path)}],
            }
        },
    )
    _insert_notice(sqlite_engine, "PROD-KEEP-1")
    with sqlite_engine.begin() as conn:
        conn.execute(
            insert(notice_spec_items).values(
                notice_no="E2E-CLEAN-1",
                item_key="voltage",
                label="정격전압",
                status="candidate",
                evidence={},
            )
        )
        conn.execute(
            insert(notice_exports).values(
                notice_no="E2E-CLEAN-1",
                kind="excel",
                draft_id="technical_compliance",
                output_path=str(export_path),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        )
        conn.execute(
            insert(notice_errors).values(
                notice_no="E2E-CLEAN-1",
                stage="documents.test",
                detail="boom",
                raw={},
            )
        )
        job_result = conn.execute(
            insert(attachment_fetch_jobs).values(
                notice_no="E2E-CLEAN-1",
                status="completed",
            )
        )
        conn.execute(
            insert(attachment_fetch_files).values(
                job_id=job_result.inserted_primary_key[0],
                notice_no="E2E-CLEAN-1",
                filename="spec.pdf",
                url="data:application/pdf;base64,",
                status="success",
            )
        )

    response = client.post("/notices/e2e/cleanup")

    assert response.status_code == 200, response.text
    assert response.json()["deleted_notices"] == 1
    assert response.json()["deleted_files"] == 2
    assert not upload_path.exists()
    assert not export_path.exists()
    assert common_path.exists()
    with sqlite_engine.begin() as conn:
        notices = conn.execute(select(bid_pipeline.c.notice_no)).scalars().all()
        spec_items = conn.execute(select(notice_spec_items.c.notice_no)).scalars().all()
        exports = conn.execute(select(notice_exports.c.notice_no)).scalars().all()
        errors = conn.execute(select(notice_errors.c.notice_no)).scalars().all()
        jobs = conn.execute(select(attachment_fetch_jobs.c.notice_no)).scalars().all()
        files = conn.execute(select(attachment_fetch_files.c.notice_no)).scalars().all()
    assert notices == ["PROD-KEEP-1"]
    assert spec_items == []
    assert exports == []
    assert errors == []
    assert jobs == []
    assert files == []
