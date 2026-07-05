"""G2B 첨부 수집 — 첨부 다운로드/분석 잡 기록 및 실행."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select, update

from api.db import require_engine
from api.models.notices import (
    AttachmentFetchFileResult,
    AttachmentFetchResponse,
    UploadedDocument,
)
from api.services.document_automation import analyze_document_requirements
from api.services.g2b_attachments import (
    bytes_stream,
    download_g2b_attachment,
    iter_g2b_attachments,
)
from api.services.status import advance_status
from api.services.uploads import (
    analyze_upload,
    build_metadata,
    merge_into_document_automation,
    remove_from_document_automation,
    save_stream,
)
from api.tables import (
    attachment_fetch_files,
    attachment_fetch_jobs,
    bid_pipeline,
    notice_errors,
)

from . import _common
from ._common import (
    _load_or_create_document_automation,
    _persist_document_automation,
    _record_errors,
)

router = APIRouter()


def _create_attachment_job(conn, notice_no: str) -> int:
    result = conn.execute(
        attachment_fetch_jobs.insert().values(
            notice_no=notice_no,
            status="running",
            started_at=datetime.now(tz=UTC),
            created_by="system",
        )
    )
    return int(result.inserted_primary_key[0])


def _create_attachment_file_result(
    conn,
    *,
    job_id: int,
    notice_no: str,
    filename: str,
    url: str,
) -> int:
    result = conn.execute(
        attachment_fetch_files.insert().values(
            job_id=job_id,
            notice_no=notice_no,
            filename=filename,
            url=url,
            status="pending",
        )
    )
    return int(result.inserted_primary_key[0])


def _update_attachment_file_result(
    conn,
    file_id: int,
    *,
    status: str,
    upload_id: str | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        update(attachment_fetch_files)
        .where(attachment_fetch_files.c.id == file_id)
        .values(
            status=status,
            upload_id=upload_id,
            error=error,
            updated_at=datetime.now(tz=UTC),
        )
    )


def _finish_attachment_job(conn, job_id: int, status: str) -> None:
    conn.execute(
        update(attachment_fetch_jobs)
        .where(attachment_fetch_jobs.c.id == job_id)
        .values(status=status, finished_at=datetime.now(tz=UTC))
    )


def _attachment_file_models(conn, job_id: int) -> list[AttachmentFetchFileResult]:
    rows = conn.execute(
        select(attachment_fetch_files)
        .where(attachment_fetch_files.c.job_id == job_id)
        .order_by(attachment_fetch_files.c.id)
    ).mappings().all()
    return [
        AttachmentFetchFileResult(
            id=int(row["id"]),
            filename=str(row["filename"]),
            url=str(row["url"]),
            status=row["status"],
            upload_id=row.get("upload_id"),
            error=row.get("error"),
            source_ref="g2b_attachment",
        )
        for row in rows
    ]


@router.post("/{notice_no}/attachments/fetch", response_model=AttachmentFetchResponse)
def fetch_g2b_attachments(notice_no: str) -> AttachmentFetchResponse:
    engine = require_engine()
    with engine.begin() as conn:
        row, analysis, document_automation = _load_or_create_document_automation(
            conn,
            notice_no,
        )
        attachments = iter_g2b_attachments(row["raw"])
        job_id = _create_attachment_job(conn, notice_no)
        fetched: list[UploadedDocument] = []
        errors: list[dict[str, Any]] = []

        # 재실행은 진짜 "재시도"여야 한다 → 이전 첨부 오류를 먼저 해소(resolved)하고,
        # 이번 실행에서 여전히 실패하는 것만 다시 기록한다. 이렇게 해야 에이전트 복구 후
        # 재분석 시 "서류 처리 오류 N건" 카운트가 실제로 줄어든다.
        conn.execute(
            update(notice_errors)
            .where(
                notice_errors.c.notice_no == notice_no,
                notice_errors.c.resolved_at.is_(None),
                notice_errors.c.stage.in_(
                    ("g2b_attachment_fetch", "g2b_attachment_analysis")
                ),
            )
            .values(resolved_at=datetime.now(tz=UTC))
        )

        existing_uploads = [
            item
            for item in (document_automation.get("uploads") or [])
            if isinstance(item, dict)
        ]
        existing_by_name = {
            str(item.get("name") or ""): item
            for item in existing_uploads
            if item.get("source_ref") == "g2b_attachment"
        }

        def _is_hwp(name: str) -> bool:
            return (
                "." in name
                and name.rsplit(".", 1)[-1].strip().lower() in {"hwp", "hwpx"}
            )

        def _existing_healthy(name: str) -> bool:
            """이미 받은 g2b 첨부가 '정상'인지(=재처리 불필요) 판정.

            정상 = 텍스트 추출 오류가 없고 파일이 디스크에 존재. 이전 실패(에이전트
            미연결 등)나 경로 이전(컨테이너→호스트)으로 파일이 없으면 재다운로드/재분석한다.
            또한 텍스트 추출 대상(pdf/hwp)인데 text_excerpt가 없으면(구버전 업로드) 본문 기반
            서류 판정을 위해 재처리한다.
            """
            item = existing_by_name.get(name)
            if not item:
                return False
            up = UploadedDocument.model_validate(item)
            on_disk = bool(up.storage_path) and Path(up.storage_path).exists()
            if up.text_extract_error or not on_disk:
                return False
            ext = name.rsplit(".", 1)[-1].strip().lower() if "." in name else ""
            if ext in {"pdf", "hwp", "hwpx"} and not up.text_excerpt:
                return False
            return True

        # HWP 에이전트 health를 한 번만 확인 → 미연결 시 파일마다 connect 재시도로
        # 시간 낭비하지 않고, 모호한 경고 N건을 명확한 1건으로 축약한다.
        # 새로 받을 .hwp뿐 아니라 '재처리 대상'(이전 실패/파일 유실)도 포함해 판단한다.
        hwp_client = _common._make_hwp_agent_client()
        needs_hwp = any(
            _is_hwp(a.filename) and not _existing_healthy(a.filename)
            for a in attachments
        )
        hwp_ok: bool | None = hwp_client.health() if needs_hwp else None
        hwp_unreachable = 0

        updated_docs = document_automation
        for attachment in attachments:
            file_id = _create_attachment_file_result(
                conn,
                job_id=job_id,
                notice_no=notice_no,
                filename=attachment.filename,
                url=attachment.url,
            )
            existing = existing_by_name.get(attachment.filename)
            if existing and _existing_healthy(attachment.filename):
                existing_upload = UploadedDocument.model_validate(existing)
                fetched.append(existing_upload)
                _update_attachment_file_result(
                    conn,
                    file_id,
                    status="skipped",
                    upload_id=existing_upload.id,
                )
                continue
            if existing:
                # 이전 실패/유실 → 오래된 업로드 항목을 제거하고 아래에서 새로 받는다.
                updated_docs, _ = remove_from_document_automation(
                    updated_docs, UploadedDocument.model_validate(existing).id
                )

            try:
                downloaded = download_g2b_attachment(attachment)
                saved = save_stream(
                    bytes_stream(downloaded.content),
                    notice_no=notice_no,
                    original_name=attachment.filename,
                )
                analysis_meta = analyze_upload(
                    saved=saved,
                    original_name=attachment.filename,
                    checklist=list(updated_docs.get("checklist") or []),
                    explicit_item_id=None,
                    hwp_client=hwp_client,
                    hwp_available=hwp_ok,
                )
                resolved_item_id = str(analysis_meta.pop("item_id") or "") or None
                uploaded = build_metadata(
                    saved,
                    original_name=attachment.filename,
                    mime=downloaded.mime,
                    item_id=resolved_item_id,
                    source_ref="g2b_attachment",
                    **analysis_meta,
                )
                updated_docs = merge_into_document_automation(updated_docs, uploaded)
                fetched.append(uploaded)
                _update_attachment_file_result(
                    conn,
                    file_id,
                    status="success",
                    upload_id=uploaded.id,
                    error=uploaded.text_extract_error,
                )
                if uploaded.text_extract_error:
                    if (
                        hwp_ok is False
                        and uploaded.text_extract_error == "HWP 에이전트 미연결"
                    ):
                        # 미연결은 루프 후 단일 요약 경고로 합친다 (파일별 중복 방지).
                        hwp_unreachable += 1
                    else:
                        errors.append(
                            {
                                "stage": "g2b_attachment_analysis",
                                "severity": "warning",
                                "source": "upload_analysis",
                                "file_name": attachment.filename,
                                "url": attachment.url,
                                "detail": uploaded.text_extract_error,
                            }
                        )
            except Exception as exc:  # noqa: BLE001
                detail = str(exc)
                errors.append(
                    {
                        "stage": "g2b_attachment_fetch",
                        "source": "g2b",
                        "file_name": attachment.filename,
                        "url": attachment.url,
                        "detail": detail,
                    }
                )
                _update_attachment_file_result(
                    conn,
                    file_id,
                    status="failed",
                    error=detail,
                )

        if hwp_unreachable:
            errors.append(
                {
                    "stage": "g2b_attachment_analysis",
                    "severity": "warning",
                    "source": "upload_analysis",
                    "detail": (
                        f"HWP 에이전트 미연결 ({hwp_client.base_url}) — "
                        "데스크톱 에이전트를 실행한 뒤 첨부 재분석을 다시 실행하세요. "
                        f"영향 .hwp {hwp_unreachable}건"
                    ),
                }
            )

        if not attachments:
            errors.append(
                {
                    "stage": "g2b_attachment_fetch",
                    "source": "g2b",
                    "detail": "G2B raw에 지원 가능한 첨부 URL이 없습니다.",
                }
            )

        # document_automation["errors"]는 UI가 읽는 저장소다. append만 하면 과거 실패가
        # 영원히 누적되므로, 이 엔드포인트가 만드는 단계(fetch/analysis)의 묵은 오류는
        # 버리고 이번 실행 결과로 교체한다. 다른 단계(autofill 등) 오류는 보존.
        _owned_stages = {"g2b_attachment_fetch", "g2b_attachment_analysis"}
        preserved_errors = [
            e
            for e in (updated_docs.get("errors") or [])
            if isinstance(e, dict) and e.get("stage") not in _owned_stages
        ]
        updated_docs = dict(updated_docs)
        updated_docs["errors"] = preserved_errors + errors
        if errors:
            _record_errors(conn, notice_no, errors)

        # 첨부 본문 반영: 방금 받은 첨부의 text_excerpt를 근거로 체크리스트(필수/필요)를 재판정.
        # analyze_document_requirements는 uploads/exports/수동변경을 보존하되 errors는 자체
        # 생성하므로, 위에서 관리한 errors를 합쳐 보존한다.
        managed_errors = list(updated_docs.get("errors") or [])
        refreshed_row = dict(row)
        refreshed_analysis = dict(analysis)
        refreshed_analysis["document_automation"] = updated_docs
        refreshed_row["analysis"] = refreshed_analysis
        reevaluated = analyze_document_requirements(refreshed_row)
        reeval_errors = [
            e for e in (reevaluated.get("errors") or []) if isinstance(e, dict)
        ]
        reevaluated["errors"] = managed_errors + reeval_errors
        updated_docs = reevaluated

        _persist_document_automation(conn, notice_no, analysis, updated_docs)
        job_status = "completed_with_errors" if errors else "completed"
        _finish_attachment_job(conn, job_id, job_status)
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(status=advance_status(row["status"], "attachments_fetched"))
        )
        return AttachmentFetchResponse(
            notice_no=notice_no,
            job_id=job_id,
            status=job_status,
            files=_attachment_file_models(conn, job_id),
            fetched=fetched,
            errors=errors,
        )
