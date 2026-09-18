"""HWPX form I/O: safe parsing, slot detection, text writing and readback."""

from __future__ import annotations

import hashlib
import io
import re

from defusedxml.ElementTree import fromstring as safe_xml

from api.parsing.attachment_text import checked_archive
from api.workspace.errors import fail

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
FORM = re.compile(r"^[<\[〈【]\s*서식\s*\d+(?:\s*[-–]\s*\d+)?\s*[>\]〉】]$")
PROTECTED = re.compile(r"주민\s*등록|서명|날인|직인|인감|\(\s*인\s*\)|증명서|확인서")
MAX_XML = 8_000_000


def _etree():
    try:
        from lxml import etree
    except ImportError:
        fail("form_dependency_missing", "원본 양식 처리 모듈(lxml)이 설치되지 않았습니다.")
    return etree


def _parse(data: bytes):
    if len(data) > MAX_XML:
        fail("form_xml_limit", "양식 XML 크기가 처리 한도를 넘었습니다.")
    # Validate every XML document with DTD/entity prohibitions before preserving its prefixes.
    safe_xml(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    etree = _etree()
    root = etree.fromstring(data, etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False,
        remove_blank_text=False, strip_cdata=False,
    ))
    if sum(1 for _ in root.iter()) > 100000:
        fail("form_xml_limit", "양식 XML 요소 수가 처리 한도를 넘었습니다.")
    return root


def _text(node) -> str:
    return "".join(node.itertext())


def _paragraph_text(node) -> str:
    return "".join(_text(t) for t in node.findall("hp:run/hp:t", NS))


def _archive(content: bytes):
    archive = checked_archive(content)
    try:
        if archive.read("mimetype").strip() != b"application/hwp+zip":
            fail("invalid_hwpx", "HWPX 원본 형식을 확인할 수 없습니다.")
        if any("signature" in name.lower() for name in archive.namelist()):
            fail("signed_hwpx", "전자서명된 원본 양식은 수정하지 않습니다.")
        roots = {}
        for entry in archive.infolist():
            if entry.filename.lower().endswith((".xml", ".hpf", ".rdf")):
                root = _parse(archive.read(entry))
                if re.fullmatch(r"Contents/section\d+\.xml", entry.filename):
                    roots[entry.filename] = root
        if not roots:
            fail("invalid_hwpx", "HWPX 본문 섹션이 없습니다.")
        return archive, roots
    except Exception:
        archive.close()
        raise


def _candidate(fields: list[dict], root, member: str, sha256: str,
               node, label: str, context: str, kind: str) -> None:
    if (not label.strip() or PROTECTED.search(re.sub(r"\s", "", label))
            or PROTECTED.search(re.sub(r"\s", "", context))):
        return
    if len(fields) >= 200:
        fail("form_field_limit", "양식 항목 수가 처리 한도를 넘었습니다.")
    location = member + "|" + root.getroottree().getpath(node)
    fields.append({
        "id": "form-" + hashlib.sha256((sha256 + "|" + location).encode()).hexdigest()[:32],
        "label": label.strip(), "context": context.strip(), "original": _text(node),
        "location": location, "kind": kind,
    })


def _fields(roots: dict, sha256: str) -> list[dict]:
    fields: list[dict] = []
    context, heading, item_label = "", "", ""
    for member, root in sorted(roots.items()):
        for paragraph in root.findall("hp:p", NS):
            plain = _paragraph_text(paragraph).strip()
            if FORM.fullmatch(plain):
                context, heading, item_label = plain, "", ""
                continue
            if not context:
                continue
            if plain and not heading and len(plain) < 100 and not re.match(r"20\d\d\s*\.", plain):
                heading = plain
            if not heading:
                title_tables = paragraph.findall(".//hp:tbl", NS)
                if title_tables and len(_text(title_tables[0]).strip()) < 100:
                    heading = _text(title_tables[0]).strip()
            full_context = f"{context} {heading}".strip()
            if re.fullmatch(r"항목\s*\d+\s*[.．]?", plain):
                item_label = plain
            if (item_label and "작성지침" in plain and "자유롭게" in plain
                    and len(plain) < 300):
                _candidate(fields, root, member, sha256, paragraph,
                           item_label, full_context, "paragraph")
                item_label = ""
            elif re.fullmatch(r"20\d\d\s*\.\s*00\s*\.\s*00\s*\.?", plain):
                _candidate(fields, root, member, sha256, paragraph,
                           "작성일자", full_context, "date")
            for table in paragraph.findall(".//hp:tbl", NS):
                if any(ancestor.tag == f"{{{HP}}}tbl" for ancestor in table.iterancestors()):
                    continue
                for row in table.findall("hp:tr", NS):
                    previous_label = ""
                    for cell in row.findall("hp:tc", NS):
                        text = " ".join(_paragraph_text(p).strip()
                                        for p in cell.findall("hp:subList/hp:p", NS)).strip()
                        if text:
                            previous_label = text
                            if re.search(r"\(\s*\)", text) and len(text) < 120:
                                _candidate(fields, root, member, sha256, cell,
                                           text, full_context, "choice")
                            continue
                        if cell.find(".//hp:tbl", NS) is not None:
                            continue
                        span = cell.find("hp:cellSpan", NS)
                        colspan = int(span.get("colSpan", "1")) if span is not None else 1
                        label = previous_label
                        if not label and colspan >= 3 and "연혁" in full_context:
                            label = "주요연혁"
                        if label:
                            _candidate(fields, root, member, sha256, cell,
                                       label, full_context, "cell")
    known = {field["id"] for field in fields}
    fields.extend(field for field in _cost_fields(roots, sha256) if field["id"] not in known)
    return fields


def _cost_fields(roots: dict, sha256: str) -> list[dict]:
    """Explicit bill-of-costs only: never infer editable prices from specification tables."""
    fields: list[dict] = []
    for member, root in roots.items():
        titles = {re.sub(r"\s", "", _paragraph_text(p)) for p in root.findall("hp:p", NS)}
        if not titles.intersection({"산출내역서", "산출공내역서", "공내역서"}):
            continue
        for table in root.findall(".//hp:tbl", NS):
            if any(a.tag == f"{{{HP}}}tbl" for a in table.iterancestors()):
                continue
            rows = table.findall("hp:tr", NS)
            if not rows or len(rows) > 100:
                continue
            header = {}
            for cell in rows[0].findall("hp:tc", NS):
                addr = cell.find("hp:cellAddr", NS)
                span = cell.find("hp:cellSpan", NS)
                label = re.sub(r"\s", "", _text(cell))
                if addr is not None and (span is None or span.get("colSpan", "1") == "1"):
                    header[label] = int(addr.get("colAddr", "-1"))
            if not {"품명", "수량", "단가", "금액"}.issubset(header):
                continue
            if len({header[k] for k in ("품명", "수량", "단가", "금액")}) != 4:
                continue
            for row in rows[1:]:
                cells = {}
                for cell in row.findall("hp:tc", NS):
                    addr = cell.find("hp:cellAddr", NS)
                    if addr is not None:
                        cells[int(addr.get("colAddr", "-1"))] = cell
                cell_texts = {column: _text(cell).strip() for column, cell in cells.items()}
                item = cell_texts.get(header["품명"], "")
                quantity = cell_texts.get(header["수량"], "")
                summary = re.sub(r"\s", "", cell_texts.get(header["단가"], ""))
                if item and re.fullmatch(r"[1-9]\d*(?:\.\d+)?", quantity):
                    targets = [(header[k], f"{item[:160]} · {k}") for k in ("단가", "금액")]
                    context = f"산출내역서 · 원본 수량 {quantity} · 자동 가격 계산 없음"
                elif summary in {"공급가액", "부가가치세", "부가세", "합계", "총계"}:
                    targets = [(header["금액"], summary)]
                    context = "산출내역서 · 합산/세액은 실제 견적 근거로 입력"
                else:
                    continue
                for column, label in targets:
                    cell = cells.get(column)
                    if cell is None or cell_texts.get(column) or cell.find(".//hp:tbl", NS) is not None:
                        continue
                    span = cell.find("hp:cellSpan", NS)
                    if span is not None and any(span.get(k, "1") != "1" for k in ("rowSpan", "colSpan")):
                        continue
                    _candidate(fields, root, member, sha256, cell, label, context, "amount")
    return fields


def _write_text(node, value: str) -> None:
    etree = _etree()
    paragraphs = [node] if node.tag == f"{{{HP}}}p" else node.findall("hp:subList/hp:p", NS)
    if not paragraphs:
        fail("form_slot_invalid", "작성 칸의 원본 문단이 없습니다.")
    paragraph = paragraphs[0]
    runs = paragraph.findall("hp:run", NS)
    if not runs:
        fail("form_slot_invalid", "작성 칸의 원본 글자 서식이 없습니다.")
    for p in paragraphs:
        for t in p.findall("hp:run/hp:t", NS):
            t.text = None
            for child in list(t):
                t.remove(child)
        # Line geometry is computed content cache; retain style/paragraph/table properties.
        for segments in p.findall("hp:linesegarray", NS):
            p.remove(segments)
    first = runs[0].find("hp:t", NS)
    if first is None:
        first = etree.SubElement(runs[0], f"{{{HP}}}t")
    parts = value.split("\n")
    first.text = parts[0]
    for part in parts[1:]:
        etree.SubElement(first, f"{{{HP}}}lineBreak").tail = part


def _readback(node) -> str:
    output = []
    for t in node.findall(".//hp:t", NS):
        output.append(t.text or "")
        for child in t:
            if child.tag == f"{{{HP}}}lineBreak":
                output.append("\n")
            output.append(child.tail or "")
    return "".join(output)


def _preview_notice() -> bytes:
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (600, 240), "#f4f6fa")
    ImageDraw.Draw(image).multiline_text(
        (35, 65), "REVIEW COPY\n\nOpen the HWPX in Hangul to review layout.\nNot approved for submission.",
        fill="#1d3557", spacing=8,
    )
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
