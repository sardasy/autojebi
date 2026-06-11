"""G2B raw에서 첫 첨부 파일을 다운받아 텍스트로 추출.

호출자(ClaudeAnalyzer)를 보호하기 위해 어떤 단계든 실패하면 None 반환 + 로그.
절대 예외를 던지지 않는다.

.hwp → milim-hwp-agent의 /document/analyze-file 응답에서 text/content/body 키 탐색.
       (현재 agent의 analyze_document는 placeholder 탐지용이라 본문이 없을 가능성
       있음 — 그 경우 응답을 JSON 직렬화해 약신호로만 사용. milim-hwp-agent에
       본문 추출 엔드포인트 추가는 별도 작업.)
.pdf → pdfplumber로 텍스트 추출.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx

from api.config import settings
from api.llm.extractor import extract_pdf_text
from api.services.hwp_agent_client import HwpAgentClient, HwpAgentError

log = logging.getLogger(__name__)


_BODY_TEXT_KEYS = ("text", "content", "body", "extracted_text", "body_text")


def fetch_first_attachment_text(
    raw: dict[str, Any] | None,
    hwp_client: HwpAgentClient | None = None,
) -> str | None:
    """G2B raw에서 ntceSpecDocUrl1 + ntceSpecFileNm1로 첫 첨부 텍스트 반환.

    URL 또는 파일명이 비어있으면 None.
    """
    if not raw:
        return None

    url = (raw.get("ntceSpecDocUrl1") or "").strip()
    fname = (raw.get("ntceSpecFileNm1") or "").strip()
    if not url or not fname:
        return None

    suffix = _file_suffix(fname).lower()
    if suffix not in (".hwp", ".hwpx", ".pdf"):
        log.info("[attachments] 지원하지 않는 확장자 %s — skip", suffix)
        return None

    download_dir = settings.g2b_attachment_dir.strip() or tempfile.gettempdir()
    local_path = Path(download_dir) / f"g2b-{uuid.uuid4().hex}{suffix}"

    try:
        if not _download(url, local_path):
            return None

        if suffix in (".hwp", ".hwpx"):
            return _extract_hwp_text(local_path, hwp_client)
        # .pdf
        try:
            return extract_pdf_text(local_path.read_bytes())
        except Exception as exc:  # noqa: BLE001
            log.warning("[attachments] PDF 추출 실패 %s: %s", local_path.name, exc)
            return None
    finally:
        try:
            if local_path.exists():
                local_path.unlink()
        except OSError as exc:
            log.warning("[attachments] 임시 파일 삭제 실패 %s: %s", local_path, exc)


def _file_suffix(fname: str) -> str:
    _, ext = os.path.splitext(fname)
    return ext or ""


def _download(url: str, dest: Path) -> bool:
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            log.info("[attachments] downloaded %s (%d bytes)", dest.name, len(resp.content))
            return True
    except Exception as exc:  # noqa: BLE001
        log.warning("[attachments] download 실패 %s: %s", url, exc)
        return False


def _extract_hwp_text(path: Path, hwp_client: HwpAgentClient | None) -> str | None:
    client = hwp_client or HwpAgentClient()
    try:
        body = client.analyze_document(str(path))
    except HwpAgentError as exc:
        log.warning("[attachments] hwp_agent analyze_document 실패: %s", exc)
        return None

    if not isinstance(body, dict):
        return None

    for key in _BODY_TEXT_KEYS:
        val = body.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    # 본문 텍스트 키 없음 — best-effort로 응답 전체를 약신호로 직렬화.
    log.info("[attachments] hwp_agent 응답에 본문 키 없음, JSON 직렬화로 약신호 사용")
    try:
        return json.dumps(body, ensure_ascii=False)[:6000]
    except (TypeError, ValueError):
        return None
