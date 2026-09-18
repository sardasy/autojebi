"""Attachment fetch job: download declared G2B attachments into the source store."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from api.config import settings
from api.services import uploads
from api.services.g2b_attachments import iter_g2b_attachments
from api.workspace.errors import WorkspaceError
from api.workspace.storage import source_path


def fetch_sources(job: dict) -> dict:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=4),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True,
    )
    def download(url: str) -> bytes:
        with (
            httpx.Client(timeout=15, follow_redirects=False) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > settings.upload_max_bytes:
                    raise ValueError("file too large")
                chunks.append(chunk)
            return b"".join(chunks)

    documents, warnings, inventory = [], [], []
    attachments = iter_g2b_attachments(job["snapshot"].get("raw"), include_unsupported=True)
    if not attachments:
        warnings.append("공고에 선언된 첨부파일이 없습니다. 나라장터 원문 첨부 목록을 확인하세요.")
    existing = job["snapshot"].get("documents") or []
    for attachment in attachments:
        item = {
            "index": attachment.index,
            "name": attachment.filename,
            "url": attachment.url,
            "status": "failed",
            "reason": "missing_url",
            "document_id": None,
            "sha256": None,
        }
        inventory.append(item)
        if not attachment.url:
            warnings.append(f"{attachment.filename}: 첨부 주소가 없습니다. 원문을 확인하세요.")
            continue
        try:
            parsed = urlparse(attachment.url)
            # Registered raw is untrusted; never fetch LAN addresses or arbitrary redirects.
            valid_url = (
                parsed.scheme in {"http", "https"}
                and parsed.hostname in {"www.g2b.go.kr", "g2b.go.kr"}
                and parsed.port in {None, 80, 443}
                and parsed.username is None
                and parsed.password is None
            )
        except ValueError:
            valid_url = False
        if not valid_url:
            item["reason"] = "invalid_url"
            warnings.append(f"{attachment.filename}: 나라장터 공식 첨부 주소 확인 필요")
            continue
        try:
            content = download(attachment.url)
            if not content:
                raise ValueError("empty attachment")
            checksum = hashlib.sha256(content).hexdigest()
            item["sha256"] = checksum
            # A content match never promotes company evidence to a notice source.
            candidates = (
                [
                    doc
                    for doc in [*existing, *documents]
                    if doc.get("role") == "notice_source"
                    and doc.get("sha256") == checksum
                    and doc.get("id")
                    and doc.get("storage_path")
                ]
                if Path(attachment.filename).suffix.lower().lstrip(".")
                in settings.upload_allowed_ext_set
                else []
            )
            candidates.sort(
                key=lambda doc: not (
                    doc.get("attachment_index") == attachment.index
                    and doc.get("attachment_url") == attachment.url
                )
            )
            match = None
            for candidate in candidates:
                try:
                    source_path(candidate)
                except Exception:
                    continue
                match = candidate
                break
            if match is not None:
                same_attachment = (
                    match.get("attachment_index") == attachment.index
                    and match.get("attachment_url") == attachment.url
                )
                doc = {
                    **match,
                    "id": match["id"] if same_attachment else uuid4().hex,
                    "name": match.get("name", attachment.filename)
                    if same_attachment
                    else attachment.filename,
                    "attachment_index": attachment.index,
                    "attachment_url": attachment.url,
                }
                if not same_attachment:
                    doc["confirmed"] = False
                documents.append(doc)
                item.update(
                    status="duplicate",
                    document_id=doc["id"],
                    reason="same_attachment_hash" if same_attachment else "same_hash_notice_source",
                )
                continue
            saved = uploads.save_stream(
                io.BytesIO(content), notice_no=job["notice_no"], original_name=attachment.filename
            )
            doc = uploads.build_metadata(
                saved,
                original_name=attachment.filename,
                mime=None,
                item_id=None,
                source_ref="g2b_attachment",
            ).model_dump()
            doc.update(
                role="notice_source",
                confirmed=False,
                text="",
                text_origin="unread",
                attachment_index=attachment.index,
                attachment_url=attachment.url,
            )
            documents.append(doc)
            item.update(status="downloaded", reason="downloaded", document_id=doc["id"])
        except uploads.UploadError as exc:
            unsupported = exc.status_code == 415
            item.update(
                status="unsupported" if unsupported else "failed",
                reason="unsupported_extension" if unsupported else "storage_failed",
            )
            warnings.append(
                f"{attachment.filename}: 지원하지 않는 첨부 형식입니다. 원본을 확인하세요."
                if unsupported
                else f"{attachment.filename}: 첨부 저장 실패. 원본을 직접 등록할 수 있습니다."
            )
        except Exception:
            item["reason"] = "fetch_failed"
            warnings.append(
                f"{attachment.filename}: 다운로드 실패. 원본을 직접 등록할 수 있습니다."
            )
    if attachments and not documents:
        raise WorkspaceError(
            502,
            {
                "code": "attachment_fetch_failed",
                "message": "첨부파일을 가져오지 못했습니다.",
                "next_action": "나라장터 공식 파일을 내려받아 직접 등록하세요.",
                "job_id": None,
                "source_inventory": inventory,
                "warnings": warnings,
            },
        )
    return {"documents": documents, "warnings": warnings, "source_inventory": inventory}
