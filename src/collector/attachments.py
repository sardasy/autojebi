"""공고 첨부파일 다운로드 + 파싱 (HWP/HWPX/PDF).

설계 원칙:
- 실패 graceful: 파서가 깨져도 빈 문자열 반환, 시스템 크래시 금지.
- 사이즈 한도: 단일 ATT_MAX_BYTES (20MB), 총합 ATT_TOTAL_MAX_BYTES (100MB).
- HWP 파서는 환경 의존 (pyhwpx 는 Windows COM, pyhwp/hwp5txt 는 pure Python).
  둘 다 실패하면 빈 문자열 + 경고 로그.
"""
from __future__ import annotations
import io
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


ATT_MAX_BYTES = 20 * 1024 * 1024       # 20 MB
ATT_TOTAL_MAX_BYTES = 100 * 1024 * 1024  # 100 MB


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class Attachment:
    bid_source_id: str
    filename: str
    content_type: str
    raw_bytes: bytes
    extracted_text: Optional[str] = None

    @property
    def size(self) -> int:
        return len(self.raw_bytes)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class HwpParser:
    """HWP/HWPX 텍스트 추출.

    1) pyhwpx — Windows COM 기반 (한컴 오피스 설치 필요). 환경 한정.
    2) hwp5txt CLI (pyhwp 패키지) — pure Python OLE, HWP 5.0 only.
    3) 둘 다 실패하면 빈 문자열 + 경고.
    """

    def parse(self, raw_bytes: bytes, filename: str) -> str:
        if not raw_bytes:
            return ""
        if self._is_hwpx(filename, raw_bytes):
            return self._try_hwpx(raw_bytes, filename)
        return self._try_hwp(raw_bytes, filename)

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _is_hwpx(filename: str, raw_bytes: bytes) -> bool:
        # HWPX 는 ZIP container — magic bytes "PK\x03\x04" + .hwpx 확장자
        return filename.lower().endswith(".hwpx") or raw_bytes[:2] == b"PK"

    def _try_hwpx(self, raw_bytes: bytes, filename: str) -> str:
        try:
            import zipfile
            import xml.etree.ElementTree as ET
        except ImportError:
            logger.warning("HWPX 파싱 모듈 없음")
            return ""

        try:
            chunks: list[str] = []
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                # HWPX 본문은 Contents/section*.xml 에 있음
                section_names = [n for n in z.namelist() if "section" in n.lower() and n.endswith(".xml")]
                for name in section_names:
                    try:
                        with z.open(name) as f:
                            data = f.read()
                        tree = ET.fromstring(data)
                        for elem in tree.iter():
                            if elem.text and elem.text.strip():
                                chunks.append(elem.text)
                    except Exception:
                        logger.exception("HWPX 섹션 파싱 실패 (%s)", name)
            text = "\n".join(chunks).strip()
            return text
        except Exception:
            logger.exception("HWPX 파싱 실패 (%s)", filename)
            return ""

    def _try_hwp(self, raw_bytes: bytes, filename: str) -> str:
        # 1) pyhwpx (Windows COM)
        text = self._try_pyhwpx(raw_bytes, filename)
        if text:
            return text
        # 2) hwp5txt CLI (pyhwp 패키지)
        text = self._try_hwp5txt_cli(raw_bytes, filename)
        if text:
            return text
        logger.warning("HWP 파싱 실패 — 파서 미가용 (%s)", filename)
        return ""

    def _try_pyhwpx(self, raw_bytes: bytes, filename: str) -> str:
        try:
            from pyhwpx import Hwp  # type: ignore[import-not-found]
        except ImportError:
            return ""

        with tempfile.NamedTemporaryFile(suffix=".hwp", delete=False) as tf:
            tf.write(raw_bytes)
            tmp = Path(tf.name)
        try:
            hwp = Hwp(new=False)
            hwp.open(str(tmp))
            text = hwp.get_text() or ""
            hwp.quit()
            return text
        except Exception:
            logger.exception("pyhwpx 추출 실패 (%s)", filename)
            return ""
        finally:
            tmp.unlink(missing_ok=True)

    def _try_hwp5txt_cli(self, raw_bytes: bytes, filename: str) -> str:
        if not shutil.which("hwp5txt"):
            return ""
        with tempfile.NamedTemporaryFile(suffix=".hwp", delete=False) as tf:
            tf.write(raw_bytes)
            tmp = Path(tf.name)
        try:
            proc = subprocess.run(
                ["hwp5txt", str(tmp)],
                capture_output=True, timeout=60, check=False,
            )
            if proc.returncode != 0:
                logger.warning("hwp5txt 실패 (%s): %s", filename, proc.stderr[:200])
                return ""
            return proc.stdout.decode("utf-8", errors="replace")
        except Exception:
            logger.exception("hwp5txt CLI 호출 실패 (%s)", filename)
            return ""
        finally:
            tmp.unlink(missing_ok=True)


class PdfParser:
    """pdfplumber 기반 PDF 텍스트 + 표 추출.

    표는 줄바꿈된 텍스트로 직렬화. 스캔본 (이미지 PDF) 은 텍스트 길이 0 →
    상위 호출자가 OCR 처리 별도로 결정.
    """

    def parse(self, raw_bytes: bytes) -> str:
        if not raw_bytes:
            return ""
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber 모듈 미설치 — PDF 파싱 불가")
            return ""

        try:
            chunks: list[str] = []
            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                for page_no, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    if text:
                        chunks.append(text)
                    # 표 추출 → 행 단위 join
                    for table in page.extract_tables() or []:
                        rendered = "\n".join(
                            "\t".join((c or "").strip() for c in row)
                            for row in table if row
                        )
                        if rendered.strip():
                            chunks.append(f"[표 p.{page_no}]\n{rendered}")
            text_total = "\n\n".join(chunks).strip()
            if not text_total:
                logger.warning("PDF 텍스트 추출 결과 빈값 — 스캔본 가능성")
            return text_total
        except Exception:
            logger.exception("PDF 파싱 실패")
            return ""


# 모듈 단위 싱글톤 (객체 stateless)
_HWP = HwpParser()
_PDF = PdfParser()


def parse_attachment(att: Attachment) -> Attachment:
    """content_type / 확장자 보고 디스패치, extracted_text 채워 반환."""
    ct = (att.content_type or "").lower()
    name = (att.filename or "").lower()

    if "pdf" in ct or name.endswith(".pdf"):
        att.extracted_text = _PDF.parse(att.raw_bytes)
    elif "hwp" in ct or name.endswith((".hwp", ".hwpx")):
        att.extracted_text = _HWP.parse(att.raw_bytes, att.filename)
    else:
        logger.info("미지원 첨부 타입 skip (%s, ct=%s)", att.filename, ct)
        att.extracted_text = ""
    return att


# ---------------------------------------------------------------------------
# Fetcher (G2B OpenAPI 의 첨부 파일 목록 + 다운로드)
# ---------------------------------------------------------------------------

class AttachmentFetcher:
    """나라장터 OpenAPI 의 첨부 파일 목록 + 다운로드.

    실제 G2B API 엔드포인트 / 권한 문제로 실패해도 빈 리스트 반환 (graceful).
    """

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ):
        from src.config import settings
        self.api_key = api_key or settings.data_go_kr_api_key
        self._client = client
        self._timeout = timeout

    async def fetch_attachments(self, bid_source_id: str) -> list[Attachment]:
        if not self.api_key:
            logger.warning("나라장터 API 키 미설정 — 첨부 fetch skip")
            return []

        # 실제 엔드포인트는 공공데이터포털 활용 신청 후 검증 필요.
        # 기본 구현은 try/except 로 감싸 운영 시 안전.
        try:
            file_metas = await self._list_files(bid_source_id)
        except Exception:
            logger.exception("첨부 목록 조회 실패 (bid=%s)", bid_source_id)
            return []

        downloaded: list[Attachment] = []
        total_size = 0
        for meta in file_metas:
            url = meta.get("url")
            filename = meta.get("filename", "unknown")
            ct = meta.get("content_type", "application/octet-stream")
            if not url:
                continue
            try:
                raw = await self._download(url)
            except Exception:
                logger.exception("첨부 다운로드 실패 (%s)", filename)
                continue
            if len(raw) > ATT_MAX_BYTES:
                logger.warning("첨부 사이즈 한도 초과 skip (%s, %d bytes)", filename, len(raw))
                continue
            if total_size + len(raw) > ATT_TOTAL_MAX_BYTES:
                logger.warning("첨부 총량 한도 초과 — 이후 첨부 skip")
                break
            total_size += len(raw)
            downloaded.append(Attachment(
                bid_source_id=bid_source_id,
                filename=filename,
                content_type=ct,
                raw_bytes=raw,
            ))
        return downloaded

    async def _list_files(self, bid_source_id: str) -> list[dict]:
        """G2B OpenAPI 의 파일 목록 호출. 활용신청 미승인이면 빈 리스트."""
        # NOTE: 정확한 엔드포인트는 운영 단계에서 확정. 기본은 빈 리스트로 폴백.
        return []

    async def _download(self, url: str) -> bytes:
        async def _go(client: httpx.AsyncClient) -> bytes:
            r = await client.get(url, timeout=self._timeout, follow_redirects=True)
            r.raise_for_status()
            return r.content

        if self._client is not None:
            return await _go(self._client)
        async with httpx.AsyncClient() as client:
            return await _go(client)
