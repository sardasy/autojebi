"""G2B raw 첨부 파일을 업로드 메타데이터 흐름으로 가져오기."""

from __future__ import annotations

import base64
import binascii
import io
import mimetypes
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote_to_bytes

import httpx

SUPPORTED_ATTACHMENT_EXTS = {"pdf", "hwp", "hwpx"}


@dataclass(frozen=True)
class G2BAttachment:
    index: int
    url: str
    filename: str


@dataclass(frozen=True)
class DownloadedAttachment:
    attachment: G2BAttachment
    content: bytes
    mime: str | None


def iter_g2b_attachments(raw: dict[str, Any] | None) -> list[G2BAttachment]:
    """Return supported G2B spec attachments in raw order."""
    if not isinstance(raw, dict):
        return []
    found: list[G2BAttachment] = []
    for index in range(1, 11):
        url = str(raw.get(f"ntceSpecDocUrl{index}") or "").strip()
        filename = str(raw.get(f"ntceSpecFileNm{index}") or "").strip()
        if not url:
            continue
        if not filename:
            filename = f"g2b-attachment-{index}.bin"
        ext = _extension(filename)
        if ext not in SUPPORTED_ATTACHMENT_EXTS:
            continue
        found.append(G2BAttachment(index=index, url=url, filename=filename))
    return found


def download_g2b_attachment(attachment: G2BAttachment) -> DownloadedAttachment:
    """Download an attachment.

    Data URLs are supported so E2E fixtures can stay hermetic while exercising
    the same persistence and analysis path as real G2B URLs.
    """
    if attachment.url.startswith("data:"):
        content, mime = _read_data_url(attachment.url)
        return DownloadedAttachment(attachment=attachment, content=content, mime=mime)

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(attachment.url)
        response.raise_for_status()
        mime = response.headers.get("content-type")
        return DownloadedAttachment(
            attachment=attachment,
            content=response.content,
            mime=mime or mimetypes.guess_type(attachment.filename)[0],
        )


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].strip().lower()


def _read_data_url(url: str) -> tuple[bytes, str | None]:
    header, sep, payload = url.partition(",")
    if not sep:
        raise ValueError("invalid data URL")
    mime = header[5:].split(";", 1)[0] or None
    if ";base64" in header:
        try:
            return base64.b64decode(payload, validate=True), mime
        except binascii.Error as exc:
            raise ValueError("invalid base64 data URL") from exc
    return unquote_to_bytes(payload), mime


def bytes_stream(content: bytes) -> io.BytesIO:
    return io.BytesIO(content)
