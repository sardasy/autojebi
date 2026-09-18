"""Stage 1 structural checks, not field readback or Hancom rendering certification.

The current provider contract cannot prove field enumeration, saved values, or
COM serialization/cleanup. A structurally readable document remains a warning
draft even when every requested field is reported as replaced.

To clear this warning in a later stage, the external worker must provide a
versioned saved-document verification response, bound to output_sha256:
* template_fields and saved_fields: complete enumerations from Hancom's field
  API, with occurrence identifiers for repeated field names (GetFieldList).
* readback: one {field, occurrence, value} entry per saved field, obtained by
  closing, reopening the saved output, and reading via GetFieldText. The caller
  must compare requested values and coverage, not trust a verified boolean.
* replaced/missing/remaining_placeholders and explicit errors: consistent with
  the enumeration and readback; no ignored field or failed write/save/reopen.
* execution evidence: single serialized COM owner through open/write/save/
  reopen/readback, successful save/reopen, and cleanup in finally on all paths.
  This requires worker implementation/integration tests, not an HTTP flag.

The caller can then verify the digest and all occurrences against its immutable
inputs and remove this specific warning. Human review and other draft warnings
remain separate. Stage 1 deliberately does not accept an unimplemented promise
of that contract as evidence.

Structural references: https://tech.hancom.com/python-hwp-parsing-1/ and
https://tech.hancom.com/hwpxformat/ . Record framing checks deliberately stop
short of interpreting layout, controls, or field records.
"""

from __future__ import annotations

import io
import re
import struct
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_DOCUMENT_BYTES = 50_000_000
MAX_ENTRIES = 4096
OLE_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
HWPML = "http://www.hancom.co.kr/hwpml/2011/"
OPF = "http://www.idpf.org/2007/opf/"


class HwpValidationError(ValueError):
    """A document cannot be accepted as a structurally checked draft."""


class _NoDtd(ET.TreeBuilder):
    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise HwpValidationError("XML document types are unsupported")


def _xml(content: bytes) -> ET.Element:
    return ET.fromstring(content, parser=ET.XMLParser(target=_NoDtd()))


def _hwpx(content: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if (
            len(entries) > MAX_ENTRIES
            or len(names) != len(set(names))
            or sum(entry.file_size for entry in entries) > MAX_DOCUMENT_BYTES
            or any(entry.flag_bits & 1 for entry in entries)
        ):
            raise HwpValidationError("unsupported HWPX archive")
        required = {
            "mimetype",
            "Contents/content.hpf",
            "Contents/header.xml",
            "Contents/section0.xml",
        }
        if not required.issubset(names):
            raise HwpValidationError("missing HWPX document parts")
        xml_parts = {}
        # Reading every member checks CRCs, including images and other embedded data.
        for entry in entries:
            data = archive.read(entry)
            if entry.filename == "mimetype" and data != b"application/hwp+zip":
                raise HwpValidationError("invalid HWPX mimetype")
            if entry.filename.endswith((".xml", ".hpf")):
                xml_parts[entry.filename] = _xml(data)
        header = xml_parts["Contents/header.xml"]
        package = xml_parts["Contents/content.hpf"]
        if header.tag != f"{{{HWPML}head}}head" or package.tag != f"{{{OPF}}}package":
            raise HwpValidationError("invalid HWPX document roots")
        sections = sorted(
            (name for name in names if re.fullmatch(r"Contents/section\d+\.xml", name)),
            key=lambda name: int(name.removeprefix("Contents/section").removesuffix(".xml")),
        )
        if sections != [f"Contents/section{i}.xml" for i in range(len(sections))]:
            raise HwpValidationError("incomplete HWPX sections")
        if int(header.attrib.get("secCnt", "0")) != len(sections):
            raise HwpValidationError("inconsistent HWPX section count")
        for name in sections:
            section = xml_parts[name]
            if (
                section.tag != f"{{{HWPML}section}}sec"
                or section.find(f"{{{HWPML}paragraph}}p") is None
            ):
                raise HwpValidationError("invalid HWPX body content")
        manifest = {}
        for item in package.findall(f"{{{OPF}}}manifest/{{{OPF}}}item"):
            item_id, href = item.get("id"), item.get("href", "")
            if not item_id or item_id in manifest or not href:
                raise HwpValidationError("invalid HWPX manifest")
            target = href if href in names else f"Contents/{href}"
            if target not in names:
                raise HwpValidationError("missing HWPX manifest target")
            manifest[item_id] = target
        spine = package.findall(f"{{{OPF}}}spine/{{{OPF}}}itemref")
        if any(item.get("idref") not in manifest for item in spine):
            raise HwpValidationError("invalid HWPX spine reference")
        ordered = [manifest[item.get("idref")] for item in spine]
        if [name for name in ordered if name in sections] != sections:
            raise HwpValidationError("incomplete HWPX spine")
        if "Contents/header.xml" not in manifest.values():
            raise HwpValidationError("missing HWPX header reference")
        return {"format": "hwpx", "parser": "zipfile/ElementTree", "section_count": len(sections)}


def _records(data: bytes, first_tag: int, minimum_size: int) -> bytes:
    offset, first = 0, None
    while offset < len(data):
        if len(data) - offset < 4:
            raise HwpValidationError("truncated HWP record")
        record = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        size = record >> 20
        if size == 0xFFF:
            if len(data) - offset < 4:
                raise HwpValidationError("truncated HWP extended record")
            size = struct.unpack_from("<I", data, offset)[0]
            offset += 4
        if size > len(data) - offset:
            raise HwpValidationError("truncated HWP record content")
        if first is None:
            if record & 0x3FF != first_tag or (record >> 10) & 0x3FF or size < minimum_size:
                raise HwpValidationError("invalid HWP document record")
            first = data[offset : offset + size]
        offset += size
    if first is None:
        raise HwpValidationError("empty HWP document stream")
    return first


def _hwp(content: bytes) -> dict:
    try:
        import olefile
    except ImportError:
        raise HwpValidationError("olefile is required to validate HWP output") from None

    with olefile.OleFileIO(io.BytesIO(content), raise_defects=olefile.DEFECT_INCORRECT) as ole:
        streams = ole.listdir(streams=True, storages=False)
        if len(streams) > MAX_ENTRIES or sum(ole.get_size(s) for s in streams) > MAX_DOCUMENT_BYTES:
            raise HwpValidationError("HWP streams exceed validation limits")

        def read(name: str) -> bytes:
            data = ole.openstream(name).read()
            if len(data) != ole.get_size(name):
                raise HwpValidationError("truncated HWP stream")
            return data

        header = read("FileHeader")
        if (
            len(header) != 256
            or header[:32] != b"HWP Document File".ljust(32, b"\0")
            or header[35] != 5
        ):
            raise HwpValidationError("invalid HWP FileHeader")
        flags = struct.unpack_from("<I", header, 36)[0]
        if flags & ((1 << 1) | (1 << 2) | (1 << 4) | (1 << 8) | (1 << 9)):
            raise HwpValidationError("protected HWP content cannot be validated")
        remaining = MAX_DOCUMENT_BYTES

        def unpack(name: str) -> bytes:
            nonlocal remaining
            data = read(name)
            if flags & 1:
                decoder = zlib.decompressobj(-15)
                data = decoder.decompress(data, remaining + 1)
                if not decoder.eof or decoder.unconsumed_tail:
                    raise HwpValidationError("invalid or oversized compressed HWP stream")
                # Hancom-saved streams may retain the gzip CRC32/ISIZE trailer.
                # Confirm its contents instead of accepting arbitrary trailing bytes.
                if decoder.unused_data and decoder.unused_data != struct.pack(
                    "<II", zlib.crc32(data), len(data)
                ):
                    raise HwpValidationError("invalid compressed HWP checksum trailer")
            remaining -= len(data)
            if remaining < 0:
                raise HwpValidationError("HWP content exceeds validation limits")
            return data

        properties = _records(unpack("DocInfo"), 16, 26)
        section_count = struct.unpack_from("<H", properties)[0]
        sections = [s for s in streams if len(s) == 2 and s[0] == "BodyText"]
        expected = [["BodyText", f"Section{i}"] for i in range(section_count)]
        if not expected or sorted(sections) != sorted(expected):
            raise HwpValidationError("incomplete HWP body sections")
        for section in expected:
            _records(unpack("/".join(section)), 66, 22)
        if ole.parsing_issues:
            raise HwpValidationError("OLE parser reported document defects")
        return {"format": "hwp_ole", "parser": "olefile/zlib", "section_count": section_count}


def validate_hwp_content(content: bytes, suffix: str) -> dict:
    """Check bounded container/content structure; never certify field values."""
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise HwpValidationError("missing or oversized HWP output")
    try:
        if content.startswith(OLE_MAGIC) and suffix.lower() == ".hwp":
            result = _hwp(content)
        elif content.startswith(b"PK") and suffix.lower() == ".hwpx":
            result = _hwpx(content)
        else:
            raise HwpValidationError("unsupported HWP content or extension mismatch")
    except HwpValidationError:
        raise
    except (
        OSError,
        ValueError,
        KeyError,
        EOFError,
        RuntimeError,
        zipfile.BadZipFile,
        ET.ParseError,
        zlib.error,
    ):
        raise HwpValidationError("invalid HWP document structure") from None
    return {
        **result,
        "contract_version": "hwp-stage1-v1",
        "structure": "passed",
        "field_partition": "not_checked",
        "field_enumeration": "unverified",
        "field_readback": "unverified",
        "com_execution": "unverified",
        "verified": False,
    }


def read_hwp_output(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise HwpValidationError("missing or linked HWP output")
    with path.open("rb") as stream:
        content = stream.read(MAX_DOCUMENT_BYTES + 1)
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise HwpValidationError("missing or oversized HWP output")
    return content
