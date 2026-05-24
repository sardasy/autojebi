"""PR 3: 첨부 파서 (HWP/PDF) 테스트.

- PDF: reportlab 으로 합성 1페이지 생성 → PdfParser 가 텍스트 추출
- HWPX: 최소 ZIP container 합성 → HwpParser 가 텍스트 추출
- 디스패치: content_type 으로 PdfParser/HwpParser 자동 분기
- 미지원 MIME: extracted_text = "" (크래시 금지)
"""
import io
import zipfile

import pytest

from src.collector.attachments import (
    Attachment,
    HwpParser,
    PdfParser,
    parse_attachment,
)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _make_minimal_pdf(text: str) -> bytes:
    """reportlab 없이 최소 PDF 1-page 텍스트 객체 합성.

    pdfplumber 가 인식할 수 있는 최소 구조 — 흔히 단위테스트에 쓰는 hand-crafted PDF.
    """
    # 가장 간단한 1페이지 PDF (PDF 1.4 specification)
    # 외부 라이브러리 없이 만들기 위해 텍스트는 ASCII 영문으로 한정.
    safe_text = "".join(ch if ord(ch) < 128 else "?" for ch in text)
    content_stream = f"BT /F1 12 Tf 50 750 Td ({safe_text}) Tj ET".encode("latin-1")
    objs = []

    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    objs.append(
        b"<< /Length " + str(len(content_stream)).encode() + b" >>\nstream\n"
        + content_stream + b"\nendstream"
    )
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(body)
        out.write(b"\nendobj\n")
    xref_pos = out.tell()
    out.write(b"xref\n0 " + str(len(objs) + 1).encode() + b"\n")
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        b"trailer\n<< /Size " + str(len(objs) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF\n"
    )
    return out.getvalue()


def test_pdf_parser_basic():
    pdf_bytes = _make_minimal_pdf("Hello attachment world")
    parser = PdfParser()
    text = parser.parse(pdf_bytes)
    assert "Hello attachment world" in text


def test_pdf_parser_empty_bytes_returns_empty():
    assert PdfParser().parse(b"") == ""


def test_pdf_parser_invalid_bytes_returns_empty():
    """깨진 PDF 도 크래시 없이 빈 문자열 반환."""
    assert PdfParser().parse(b"NOT A PDF") == ""


# ---------------------------------------------------------------------------
# HWPX (XML in ZIP container)
# ---------------------------------------------------------------------------

def _make_minimal_hwpx(text: str) -> bytes:
    """HWPX 의 최소 ZIP — Contents/section0.xml 안에 텍스트 노드."""
    buf = io.BytesIO()
    section_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/section">'
        f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>'
        f'</hp:sec>'
    )
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", section_xml.encode("utf-8"))
    return buf.getvalue()


def test_hwpx_parser_extracts_text():
    raw = _make_minimal_hwpx("기초금액 850,000,000원")
    text = HwpParser().parse(raw, "sample.hwpx")
    assert "기초금액" in text
    assert "850,000,000원" in text


def test_hwp_parser_unsupported_format_returns_empty():
    """pyhwpx/hwp5txt 없는 환경에서 .hwp 파싱은 빈 문자열."""
    # 실제 HWP 바이너리 없이 — 파서가 graceful 한지만 검증
    result = HwpParser().parse(b"FAKE HWP BODY", "fake.hwp")
    assert result == ""


# ---------------------------------------------------------------------------
# 디스패치
# ---------------------------------------------------------------------------

def test_dispatch_pdf_by_content_type():
    att = Attachment(
        bid_source_id="BID-1",
        filename="spec.pdf",
        content_type="application/pdf",
        raw_bytes=_make_minimal_pdf("Hi"),
    )
    parse_attachment(att)
    assert "Hi" in (att.extracted_text or "")


def test_dispatch_hwpx_by_extension():
    att = Attachment(
        bid_source_id="BID-2",
        filename="공고.hwpx",
        content_type="application/octet-stream",  # 잘못 매핑된 MIME 도 확장자로 보정
        raw_bytes=_make_minimal_hwpx("입찰공고 본문"),
    )
    parse_attachment(att)
    assert "입찰공고 본문" in (att.extracted_text or "")


def test_dispatch_unsupported_returns_empty_string():
    att = Attachment(
        bid_source_id="BID-3",
        filename="ignore.zip",
        content_type="application/zip",
        raw_bytes=b"PK\x03\x04...",
    )
    parse_attachment(att)
    assert att.extracted_text == ""
