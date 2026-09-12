import copy
import zipfile

import pytest
from lxml import etree

from tools.verify_original_form_output import HP, verify


def section():
    return etree.fromstring(
        f"""<hs:sec xmlns:hs="urn:test-section" xmlns:hp="{HP}">
      <hp:p id="1"><hp:run charPrIDRef="3"><hp:t>Original heading</hp:t></hp:run></hp:p>
      <hp:p id="2"><hp:run charPrIDRef="3"><hp:tbl id="5" rowCnt="1" colCnt="2">
        <hp:tr><hp:tc borderFillIDRef="9"><hp:subList><hp:p id="3">
          <hp:run charPrIDRef="6"/><hp:linesegarray><hp:lineseg textpos="0"/></hp:linesegarray>
        </hp:p></hp:subList><hp:cellAddr rowAddr="0" colAddr="0"/>
          <hp:cellSpan rowSpan="1" colSpan="2"/><hp:cellSz width="2000" height="1000"/>
        </hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
    </hs:sec>""".encode()
    )


def archive(path, root, *, image=b"original-image", header=None, preview=b"old-preview"):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as book:
        book.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        book.writestr("Contents/header.xml", header or b'<header><style id="9"/></header>')
        book.writestr("Contents/section0.xml", etree.tostring(root))
        book.writestr("BinData/image1.jpg", image)
        book.writestr("Preview/PrvImage.png", preview)


def filled(root):
    result = copy.deepcopy(root)
    run = result.find(f".//{{{HP}}}tc/{{{HP}}}subList/{{{HP}}}p/{{{HP}}}run")
    etree.SubElement(run, f"{{{HP}}}t").text = "Sensitive company value"
    return result


def pair(tmp_path, original=None, result=None, **options):
    original = original if original is not None else section()
    source, output = tmp_path / "source.hwpx", tmp_path / "filled.hwpx"
    archive(source, original)
    archive(output, result if result is not None else filled(original), **options)
    return source, output


def test_blank_fill_preserves_geometry_and_does_not_expose_value(tmp_path):
    source, output = pair(tmp_path)
    before = source.read_bytes()
    report = verify(source, output)
    assert report["status"] == "passed"
    assert report["text_change_count"] == 1
    assert report["sections"][0]["text_changes"][0]["change"] == "filled_blank"
    assert report["sections"][0]["tables"][0]["geometry_merge_style_preserved"]
    assert "Sensitive company value" not in str(report)
    assert source.read_bytes() == before
    assert report["visual_validation"] == "not_performed"


def test_merge_style_and_original_heading_loss_are_detected(tmp_path):
    original = section()
    result = filled(original)
    result.find(f".//{{{HP}}}cellSpan").set("colSpan", "1")
    result.find(f".//{{{HP}}}tc").set("borderFillIDRef", "12")
    result.find(f".//{{{HP}}}t").text = ""
    report = verify(*pair(tmp_path, original, result))
    codes = {issue["code"] for issue in report["issues"]}
    assert report["status"] == "failed"
    assert {
        "source_text_removed",
        "table_geometry_merge_or_style_changed",
        "protected_section_structure_changed",
    } <= codes


def test_added_paragraph_is_not_accepted_as_fill(tmp_path):
    original = section()
    result = filled(original)
    result.append(etree.Element(f"{{{HP}}}p", id="unexpected"))
    report = verify(*pair(tmp_path, original, result))
    assert "paragraph_count_changed" in {issue["code"] for issue in report["issues"]}


def test_overwritten_original_label_is_flagged_for_review(tmp_path):
    original = section()
    result = filled(original)
    result.find(f".//{{{HP}}}t").text = "Unexpected different heading"
    report = verify(*pair(tmp_path, original, result))
    assert report["status"] == "passed"  # Structure preserved; content approval remains separate.
    assert "original_text_replacement_requires_review" in {
        issue["code"] for issue in report["issues"]
    }


def test_formatting_whitespace_and_layout_cache_do_not_fail(tmp_path):
    original = section()
    result = filled(original)
    cache = result.find(f".//{{{HP}}}linesegarray")
    cache.getparent().remove(cache)
    result.text = "\n\n    "
    report = verify(
        *pair(tmp_path, original, result, header=b'<header>\n   <style id="9" />\n</header>')
    )
    assert report["status"] == "passed"
    assert report["sections"][0]["layout_cache_changed"]
    assert report["non_body_member_changes"][0]["xml_semantics_preserved"]


def test_image_loss_fails_but_changed_preview_is_separate(tmp_path):
    report = verify(*pair(tmp_path, image=b"changed-image", preview=b"new-preview"))
    assert report["status"] == "failed"
    assert report["preview_member_changes"][0]["member"] == "Preview/PrvImage.png"
    assert {issue.get("member") for issue in report["issues"]} == {"BinData/image1.jpg"}


def test_invalid_xml_is_rejected(tmp_path):
    source, output = pair(tmp_path)
    with zipfile.ZipFile(output, "a") as book:
        book.writestr("broken.xml", b"<broken>")
    report = verify(source, output)
    assert "output_xml_invalid" in {issue["code"] for issue in report["issues"]}
    assert verify(source, source)["status"] == "failed"


def test_duplicate_members_and_dtd_are_rejected(tmp_path):
    source, output = pair(tmp_path)
    with zipfile.ZipFile(output, "a") as book, pytest.warns(UserWarning, match="Duplicate name"):
        book.writestr("Contents/header.xml", b"<header/>")
    assert verify(source, output)["status"] == "failed"
    source, output = pair(
        tmp_path, header=b'<!DOCTYPE header [<!ENTITY e "bad">]><header>&e;</header>'
    )
    report = verify(source, output)
    assert "output_xml_invalid" in {issue["code"] for issue in report["issues"]}


def test_namespace_prefix_changes_are_semantically_equivalent(tmp_path):
    source, output = pair(tmp_path)
    with zipfile.ZipFile(output) as book:
        entries = [(item, book.read(item)) for item in book.infolist()]
    with zipfile.ZipFile(output, "w") as book:
        for item, content in entries:
            if item.filename == "Contents/section0.xml":
                content = content.replace(b"xmlns:hp=", b"xmlns:para=").replace(b"hp:", b"para:")
            book.writestr(item, content)
    assert verify(source, output)["status"] == "passed"
