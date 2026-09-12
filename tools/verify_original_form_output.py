"""Compare a filled HWPX with its original without opening or modifying either file.

This verifies preservation and XML readability, not Hancom rendering or bid readiness.
Values are represented by lengths and hashes so reports do not disclose filled company data.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
TEXT = f"{{{HP}}}t"
RUN = f"{{{HP}}}run"
PARAGRAPH = f"{{{HP}}}p"
CACHE = f"{{{HP}}}linesegarray"
TABLE = f"{{{HP}}}tbl"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_MEMBERS = 5000


def checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _issue(report: dict, code: str, *, severity: str = "error", **details: Any) -> None:
    report["issues"].append({"code": code, "severity": severity, **details})


def _archive(content: bytes) -> tuple[dict[str, bytes], list[zipfile.ZipInfo]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = archive.infolist()
        names = [entry.filename for entry in members]
        if len(members) > MAX_MEMBERS or sum(e.file_size for e in members) > MAX_ARCHIVE_BYTES:
            raise ValueError("archive_size_limit")
        if len(names) != len(set(names)):
            raise ValueError("duplicate_archive_members")
        if any(entry.flag_bits & 1 for entry in members):
            raise ValueError("encrypted_archive_member")
        return {entry.filename: archive.read(entry) for entry in members}, members


def _xml(content: bytes) -> etree._Element:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        recover=False,
        huge_tree=False,
        remove_blank_text=False,
    )
    root = etree.fromstring(content, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError("xml_doctype_forbidden")
    if any(isinstance(item, etree._Entity) for item in root.iter()):
        raise ValueError("xml_entity_forbidden")
    return root


def _is_xml(name: str) -> bool:
    return name.lower().endswith((".xml", ".hpf", ".rdf"))


def _section(name: str) -> bool:
    return bool(re.fullmatch(r"Contents/section\d+\.xml", name))


def _meaningful(value: str | None) -> str | None:
    return value if value and value.strip() else None


def _signature(element: etree._Element, *, ignore_text: bool = False) -> tuple:
    """Namespace-aware semantic shape; ignore serialization whitespace and prefix names."""
    if not isinstance(element.tag, str):
        return ("special", str(type(element)), _meaningful(element.text))
    children = [child for child in element if not (ignore_text and child.tag in {TEXT, CACHE})]
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        _meaningful(element.text),
        tuple(
            (_signature(child, ignore_text=ignore_text), _meaningful(child.tail))
            for child in children
        ),
    )


def _digest_object(value: Any) -> str:
    return checksum(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _path(element: etree._Element) -> str:
    """Stable local-name address; element namespaces are checked separately in shape."""
    parts = []
    while element is not None:
        parent = element.getparent()
        siblings = (
            [child for child in parent if child.tag == element.tag] if parent is not None else []
        )
        index = siblings.index(element) + 1 if parent is not None else 1
        parts.append(f"{etree.QName(element).localname}[{index}]")
        element = parent
    return "/" + "/".join(reversed(parts))


def _text(element: etree._Element) -> str:
    parts = [element.text or ""]
    for child in element:
        local = etree.QName(child).localname if isinstance(child.tag, str) else ""
        if local == "lineBreak":
            parts.append("\n")
        elif local == "tab":
            parts.append("\t")
        else:
            parts.append(_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _texts(root: etree._Element) -> dict[str, str]:
    return {
        _path(run): "".join(_text(child) for child in run if child.tag == TEXT)
        for run in root.iter(RUN)
    }


def _replacement_kind(original: str, filled: str) -> str:
    if re.search(r"\.{3,}|…{2,}", original) or re.fullmatch(
        r"\s*\d{4}\s*[.년/-]\s*00\s*[.월/-]\s*00\s*[.일]?\s*", original
    ):
        return "placeholder"

    def without_choices(value: str) -> str:
        return re.sub(r"\s+", "", re.sub(r"\([^)]*\)", "()", value))

    if re.search(r"\(\s*\)", original) and without_choices(original) == without_choices(filled):
        return "choice_mark"
    return "original_text_replaced"


def _node_changes(source: etree._Element, output: etree._Element) -> list[dict]:
    """Identify changed protected node properties, independent of text insertion."""

    def nodes(root: etree._Element) -> dict[str, tuple]:
        result = {}
        for item in root.iter():
            if not isinstance(item.tag, str) or item.tag in {TEXT, CACHE}:
                continue
            if any(parent.tag in {TEXT, CACHE} for parent in item.iterancestors()):
                continue
            result[_path(item)] = (
                item.tag,
                tuple(sorted(item.attrib.items())),
                _meaningful(item.text),
            )
        return result

    before, after = nodes(source), nodes(output)
    return [
        {
            "location": key,
            "change": "removed"
            if key not in after
            else "added"
            if key not in before
            else "changed",
            "source_sha256": _digest_object(before.get(key)),
            "output_sha256": _digest_object(after.get(key)),
        }
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    ]


def _compare_section(
    name: str, source: etree._Element, output: etree._Element, report: dict
) -> dict:
    before, after = _texts(source), _texts(output)
    text_changes = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key, ""), after.get(key, "")
        if old == new:
            continue
        kind = "filled_blank" if not old.strip() else "removed" if not new.strip() else "replaced"
        text_changes.append(
            {
                "location": key,
                "change": kind,
                "source_length": len(old),
                "output_length": len(new),
                "source_sha256": checksum(old.encode("utf-8")),
                "output_sha256": checksum(new.encode("utf-8")),
            }
        )
        if kind == "removed":
            _issue(report, "source_text_removed", member=name, location=key)
        elif kind == "replaced":
            text_changes[-1]["replacement_kind"] = _replacement_kind(old, new)
            if text_changes[-1]["replacement_kind"] == "original_text_replaced":
                _issue(
                    report,
                    "original_text_replacement_requires_review",
                    severity="warning",
                    member=name,
                    location=key,
                )

    p_counts = {
        "source": sum(1 for _ in source.iter(PARAGRAPH)),
        "output": sum(1 for _ in output.iter(PARAGRAPH)),
    }
    if p_counts["source"] != p_counts["output"]:
        _issue(report, "paragraph_count_changed", member=name, **p_counts)
    old_tables, new_tables = list(source.iter(TABLE)), list(output.iter(TABLE))
    if len(old_tables) != len(new_tables):
        _issue(report, "table_count_changed", member=name)
    tables = []
    for index in range(max(len(old_tables), len(new_tables))):
        old = old_tables[index] if index < len(old_tables) else None
        new = new_tables[index] if index < len(new_tables) else None
        old_shape = _signature(old, ignore_text=True) if old is not None else None
        new_shape = _signature(new, ignore_text=True) if new is not None else None
        same = old_shape == new_shape
        table = {
            "index": index,
            "source_id": old.get("id") if old is not None else None,
            "source_rows": old.get("rowCnt") if old is not None else None,
            "output_rows": new.get("rowCnt") if new is not None else None,
            "source_columns": old.get("colCnt") if old is not None else None,
            "output_columns": new.get("colCnt") if new is not None else None,
            "geometry_merge_style_preserved": same,
            "source_structure_sha256": _digest_object(old_shape),
            "output_structure_sha256": _digest_object(new_shape),
        }
        tables.append(table)
        if not same:
            _issue(report, "table_geometry_merge_or_style_changed", member=name, table_index=index)
    protected = _node_changes(source, output)
    structure_same = _signature(source, ignore_text=True) == _signature(output, ignore_text=True)
    if not structure_same:
        _issue(report, "protected_section_structure_changed", member=name)
    old_cache = [_signature(node) for node in source.iter(CACHE)]
    new_cache = [_signature(node) for node in output.iter(CACHE)]
    return {
        "member": name,
        "paragraph_count": p_counts,
        "table_count": {"source": len(old_tables), "output": len(new_tables)},
        "tables": tables,
        "protected_structure_preserved": structure_same,
        "protected_node_changes": protected,
        "text_change_count": len(text_changes),
        "text_changes": text_changes,
        "layout_cache_changed": old_cache != new_cache,
        "layout_cache_count": {"source": len(old_cache), "output": len(new_cache)},
    }


def verify(source_path: Path | str, output_path: Path | str) -> dict:
    source_path, output_path = Path(source_path).resolve(), Path(output_path).resolve()
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "failed",
        "issues": [],
        "visual_validation": "not_performed",
        "sections": [],
    }
    if source_path == output_path or (
        source_path.exists() and output_path.exists() and source_path.samefile(output_path)
    ):
        _issue(report, "source_and_output_must_be_distinct")
        return report
    try:
        original, filled = source_path.read_bytes(), output_path.read_bytes()
        report["source_sha256"], report["output_sha256"] = checksum(original), checksum(filled)
        source, source_info = _archive(original)
        output, output_info = _archive(filled)
        report["archive"] = {
            "source_member_count": len(source_info),
            "output_member_count": len(output_info),
            "source_members": list(source),
            "output_members": list(output),
            "missing_members": sorted(source.keys() - output.keys()),
            "added_members": sorted(output.keys() - source.keys()),
            "member_order_preserved": list(source) == list(output),
        }
        if source.keys() != output.keys():
            _issue(report, "archive_member_set_changed")
        if "mimetype" not in output or not output_info or output_info[0].filename != "mimetype":
            _issue(report, "mimetype_missing_or_not_first")
        elif output_info[0].compress_type != zipfile.ZIP_STORED:
            _issue(report, "mimetype_must_be_uncompressed")
        output_xml = {}
        report["xml_members_validated"] = []
        for name, content in output.items():
            if _is_xml(name):
                try:
                    output_xml[name] = _xml(content)
                    report["xml_members_validated"].append(name)
                except (ValueError, etree.XMLSyntaxError):
                    _issue(report, "output_xml_invalid", member=name)
        non_body = []
        previews = []
        for name in sorted(source.keys() & output.keys()):
            if _section(name):
                if name not in output_xml:
                    continue
                report["sections"].append(
                    _compare_section(name, _xml(source[name]), output_xml[name], report)
                )
            elif source[name] != output[name]:
                change = {
                    "member": name,
                    "source_sha256": checksum(source[name]),
                    "output_sha256": checksum(output[name]),
                }
                if name.startswith("Preview/"):
                    previews.append(change)
                else:
                    semantic_same = bool(
                        name in output_xml
                        and _signature(_xml(source[name])) == _signature(output_xml[name])
                    )
                    change["xml_semantics_preserved"] = semantic_same
                    non_body.append(change)
                    if not semantic_same:
                        _issue(report, "non_body_member_changed", member=name)
        report["non_body_member_changes"] = non_body
        report["preview_member_changes"] = previews
        report["preview_validation"] = "not_rendering_evidence"
        if not report["sections"]:
            _issue(report, "no_comparable_sections")
        report["text_change_count"] = sum(s["text_change_count"] for s in report["sections"])
        report["source_unchanged_after_verification"] = checksum(
            source_path.read_bytes()
        ) == checksum(original)
        if not report["source_unchanged_after_verification"]:
            _issue(report, "source_changed_during_verification")
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, etree.XMLSyntaxError) as exc:
        _issue(report, "verification_unavailable", error_type=type(exc).__name__)
    report["status"] = (
        "failed" if any(i["severity"] == "error" for i in report["issues"]) else "passed"
    )
    report["interpretation"] = (
        "Structural preservation only. Replaced text still requires source/claim review; "
        "Hancom page layout and submission readiness are not certified."
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--json", type=Path, dest="report_path", help="Write the JSON report here")
    args = parser.parse_args()
    if args.report_path:
        target = args.report_path.resolve()
        for item in (args.source, args.output):
            if target == item.resolve() or (
                target.exists() and item.exists() and target.samefile(item)
            ):
                parser.error("The JSON report path must not overwrite either input file.")
    result = verify(args.source, args.output)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report_path:
        args.report_path.write_text(encoded, encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(encoded, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
