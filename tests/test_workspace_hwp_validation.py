from __future__ import annotations

import hashlib
import io
import struct
import zipfile
import zlib
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from api.services.hwp_agent_client import HwpAgentClient, HwpAgentError, PutFieldsOutcome
from api.workspace import execution
from api.workspace.errors import WorkspaceError
from api.workspace.hwp_validation import (
    HWPML,
    OLE_MAGIC,
    OPF,
    HwpValidationError,
    validate_hwp_content,
)


def hwpx_bytes(changes=None):
    parts = {
        "mimetype": b"application/hwp+zip",
        "Contents/header.xml": f'<hh:head xmlns:hh="{HWPML}head" secCnt="1"/>'.encode(),
        "Contents/section0.xml": (
            f'<hs:sec xmlns:hs="{HWPML}section" xmlns:hp="{HWPML}paragraph">'
            "<hp:p><hp:run><hp:t>Draft content</hp:t></hp:run></hp:p></hs:sec>"
        ).encode(),
        "Contents/content.hpf": (
            f'<opf:package xmlns:opf="{OPF}"><opf:manifest>'
            '<opf:item id="header" href="header.xml"/>'
            '<opf:item id="section0" href="section0.xml"/></opf:manifest>'
            '<opf:spine><opf:itemref idref="section0"/></opf:spine></opf:package>'
        ).encode(),
    }
    parts.update(changes or {})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            if content is not None:
                archive.writestr(name, content)
    return stream.getvalue()


def hwp_bytes(
    *,
    compressed=False,
    trailer=False,
    corrupt_trailer=False,
    signature=True,
    flags=0,
    body=None,
    section_count=1,
):
    """Small CFB fixture parsed by real olefile; not a Hancom-rendered document."""
    free, end, fat_sector = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
    header = bytearray(512)
    header[:8] = OLE_MAGIC
    struct.pack_into("<HHHHH", header, 24, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<IIIIIIIII", header, 40, 0, 1, 1, 0, 4096, 3, 1, end, 0)
    struct.pack_into("<109I", header, 76, 0, *([free] * 108))
    fat = struct.pack("<128I", fat_sector, 2, end, end, end, *([free] * 123))

    def directory(name, kind, start=end, size=0, left=free, right=free, child=free):
        entry = bytearray(128)
        encoded = (name + "\0").encode("utf-16-le")
        entry[: len(encoded)] = encoded
        struct.pack_into("<HBBIII", entry, 64, len(encoded), kind, 1, left, right, child)
        struct.pack_into("<IQ", entry, 116, start, size)
        return entry

    file_header = bytearray(256)
    file_header[:32] = (b"HWP Document File" if signature else b"Word document").ljust(32, b"\0")
    struct.pack_into("<II", file_header, 32, 0x05000300, flags | int(compressed))
    docinfo = struct.pack("<IH", (26 << 20) | 16, section_count) + bytes(24)
    section = body if body is not None else struct.pack("<I", (22 << 20) | 66) + bytes(22)
    if compressed:

        def compress(data):
            checksum = zlib.crc32(data) ^ int(corrupt_trailer)
            return zlib.compress(data)[2:-4] + (
                struct.pack("<II", checksum, len(data)) if trailer else b""
            )

        docinfo = compress(docinfo)
        section = compress(section)
    assert len(docinfo) <= 64 and len(section) <= 64
    mini_stream = bytes(file_header) + docinfo.ljust(64, b"\0") + section.ljust(64, b"\0")
    directories = b"".join(
        [
            directory("Root Entry", 5, 4, len(mini_stream), child=3),
            directory("FileHeader", 2, 0, 256),
            directory("DocInfo", 2, 4, len(docinfo)),
            directory("BodyText", 1, left=2, right=1, child=4),
            directory("Section0", 2, 5, len(section)),
        ]
    ).ljust(1024, b"\0")
    mini_fat = struct.pack("<128I", 1, 2, 3, end, end, end, *([free] * 122))
    return bytes(header) + fat + directories + mini_fat + mini_stream.ljust(512, b"\0")


def provider_body(**changes):
    return {
        "output_path": "draft.hwp",
        "replaced": ["notice"],
        "missing": [],
        "remaining_placeholders": [],
        **changes,
    }


def provider_client(body):
    return HwpAgentClient(
        retries=1,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )


@pytest.mark.parametrize("key", ["output_path", "replaced", "missing", "remaining_placeholders"])
def test_client_requires_all_report_fields(key):
    body = provider_body()
    del body[key]
    with pytest.raises(HwpAgentError, match="schema"):
        provider_client(body).put_fields(
            template_path="t.hwp", output_path="o.hwp", values={"notice": "N"}
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"output_path": None},
        {"output_path": 1},
        {"output_path": " "},
        {"replaced": "notice"},
        {"missing": None},
        {"remaining_placeholders": {}},
        {"replaced": [1]},
        {"replaced": [""]},
        {"replaced": ["notice", "notice"]},
        {"missing": ["x", "x"]},
        {"fields": "notice"},
        {"ok": False},
        {"ok": "true"},
        {"success": False},
        {"status": "failed"},
        {"error": "secret-document-text"},
        {"errors": ["secret-document-text"]},
        {"replaced": []},
        {"replaced": ["unexpected"]},
        {"missing": ["notice"]},
    ],
)
def test_client_rejects_malformed_errors_and_inconsistent_partition(changes):
    with pytest.raises(HwpAgentError) as error:
        provider_client(provider_body(**changes)).put_fields(
            template_path="t.hwp", output_path="o.hwp", values={"notice": "N"}
        )
    assert "secret-document-text" not in str(error.value)


def test_client_retains_missing_template_fields():
    outcome = provider_client(
        provider_body(missing=["unmapped"], fields=["notice", "unmapped"])
    ).put_fields(template_path="t.hwp", output_path="o.hwp", values={"notice": "N"})
    assert outcome.missing == ["unmapped"]
    assert outcome.raw["fields"] == ["notice", "unmapped"]


@pytest.mark.parametrize("body", [{}, {"ok": "false"}, {"ok": 1}, {"ok": True, "error": "failure"}])
def test_health_requires_literal_success(body):
    assert provider_client(body).health() is False


def test_legacy_fill_and_compose_do_not_default_missing_reports_or_counts():
    with pytest.raises(HwpAgentError):
        provider_client({}).autofill_bid_form(template_path="t", output_path="o", values={})
    with pytest.raises(HwpAgentError):
        provider_client(provider_body()).compose_proposal(
            template_path="t", output_path="o", values={}, sections=[], tables=[]
        )
    outcome = provider_client(provider_body(section_count=0, table_count=0)).compose_proposal(
        template_path="t", output_path="o", values={}, sections=[{"title": "section"}], tables=[]
    )
    assert outcome.section_count == 0


@pytest.mark.parametrize("compressed,trailer", [(False, False), (True, False), (True, True)])
def test_real_ole_parser_checks_hwp_streams(compressed, trailer):
    result = validate_hwp_content(hwp_bytes(compressed=compressed, trailer=trailer), ".hwp")
    assert result["format"] == "hwp_ole"
    assert result["section_count"] == 1
    assert result["structure"] == "passed"
    assert result["verified"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"signature": False},
        {"flags": 2},
        {"flags": 4},
        {"section_count": 2},
        {"body": b"arbitrary bytes"},
        {"body": b""},
        {"body": struct.pack("<I", (100 << 20) | 66) + b"short"},
        {"compressed": True, "trailer": True, "corrupt_trailer": True},
    ],
)
def test_ole_container_alone_is_not_a_valid_hwp(changes):
    with pytest.raises(HwpValidationError):
        validate_hwp_content(hwp_bytes(**changes), ".hwp")


@pytest.mark.parametrize(
    "content,suffix",
    [
        (b"", ".hwp"),
        (b"mock-hwp-not-a-real-document", ".hwp"),
        (OLE_MAGIC + bytes(100), ".hwp"),
        (b"PK\x03\x04garbage", ".hwpx"),
        (hwpx_bytes(), ".hwp"),
        (hwp_bytes(), ".hwpx"),
        (hwp_bytes()[:600], ".hwp"),
    ],
)
def test_invalid_content_or_wrong_extension_is_rejected(content, suffix):
    with pytest.raises(HwpValidationError):
        validate_hwp_content(content, suffix)


@pytest.mark.parametrize(
    "changes",
    [
        {"mimetype": b"application/zip"},
        {"Contents/header.xml": None},
        {"Contents/content.hpf": b"<package/>"},
        {"Contents/section0.xml": b"broken XML"},
        {"Contents/section0.xml": b"<document>not HWPX</document>"},
        {"Contents/section1.xml": b"<unexpected/>"},
        {"Contents/header.xml": f'<head xmlns="{HWPML}head" secCnt="2"/>'.encode()},
        {
            "Contents/section0.xml": '<!DOCTYPE foo [<!ENTITY x "data">]><foo>&x;</foo>'.encode(
                "utf-16"
            )
        },
        {
            "Contents/content.hpf": (
                f'<package xmlns="{OPF}"><manifest><item id="s" href="missing.xml"/></manifest>'
                '<spine><itemref idref="s"/></spine></package>'
            ).encode()
        },
    ],
)
def test_hwpx_requires_parseable_document_parts_and_references(changes):
    with pytest.raises(HwpValidationError):
        validate_hwp_content(hwpx_bytes(changes), ".hwpx")


def test_valid_hwpx_is_structurally_checked_but_not_verified():
    result = validate_hwp_content(hwpx_bytes(), ".hwpx")
    assert result["format"] == "hwpx"
    assert result["field_readback"] == "unverified"
    assert result["com_execution"] == "unverified"
    assert result["verified"] is False


@pytest.fixture
def run_context(tmp_path, monkeypatch):
    template = tmp_path / "template.hwpx"
    template.write_bytes(hwpx_bytes())
    folder = tmp_path / "output"
    folder.mkdir()
    preview = {
        "template": {
            "id": 1,
            "template_path": str(template),
            "kind": "bid_form",
            "template_version": "v1",
        },
        "values": {"notice": "N"},
        "required_missing": [],
        "body_mapped": True,
        "mappings": [{"hwp_field_name": "notice", "required": True}],
    }
    conn = SimpleNamespace(execute=lambda query: SimpleNamespace(scalars=lambda: ["notice"]))
    engine = SimpleNamespace(begin=lambda: nullcontext(conn))
    monkeypatch.setenv("HWP_AGENT_TOKEN", "test-token")
    monkeypatch.setenv("HWP_TEMPLATE_ROOT", str(tmp_path))
    monkeypatch.setattr(execution, "hwp_preview", lambda *args: preview)
    monkeypatch.setattr(execution, "blockers", lambda snapshot: [])
    state = SimpleNamespace(
        content=hwpx_bytes(),
        report={},
        calls=0,
        engine=engine,
        folder=folder,
        preview=preview,
        job={"snapshot": {}, "parameters": {"template_key": "bid_form"}},
    )

    class Worker:
        def __init__(self, **kwargs):
            assert kwargs["retries"] == 1

        def health(self):
            return True

        def inspect_fields(self, path):
            return {"sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                    "fields": ["notice"], "field_occurrences": [{"field": "notice", "occurrence": 0}]}

        def put_fields(self, **kwargs):
            state.calls += 1
            if state.content is not None:
                Path(kwargs["output_path"]).write_bytes(state.content)
            report = provider_body(output_path=kwargs["output_path"], **state.report)
            return PutFieldsOutcome(
                output_path=report["output_path"],
                replaced=report["replaced"],
                missing=report["missing"],
                remaining_placeholders=report["remaining_placeholders"],
                raw=report,
            )

    monkeypatch.setattr(execution, "HwpAgentClient", Worker)
    return state


def test_run_hwp_records_fields_and_never_marks_unverified_output_normal(run_context):
    state = run_context
    state.report = {"fields": ["notice"], "verified": True}
    result = execution.run_hwp(state.engine, state.job, state.folder)
    assert result["warnings"]
    assert result["verified"] is False
    assert result["validation"]["field_readback"] == "unverified"
    assert result["expected_fields"] == ["notice"]
    assert result["fields"] == ["notice"]
    assert result["replaced"] == ["notice"]
    assert result["input_values"] == {"notice": "N"}
    assert result["required_missing"] == []
    assert result["template_version"] == "v1"
    assert result["sha256"] == hashlib.sha256(state.content).hexdigest()
    assert result["size"] == len(state.content)
    assert Path(result["artifact"]).suffix == ".hwpx"


def saved_report(state):
    fields = [{"field": "notice", "occurrence": 0}]
    return {
        "fields": ["notice"],
        "verification": {
            "contract_version": 1,
            "template_sha256": hashlib.sha256(Path(state.preview["template"]["template_path"]).read_bytes()).hexdigest(),
            "output_sha256": hashlib.sha256(state.content).hexdigest(),
            "template_fields": fields, "saved_fields": fields,
            "readback": [{"field": "notice", "occurrence": 0, "value": "N"}],
            "lifecycle": ["opened", "written", "saved", "closed", "reopened", "readback", "closed", "quit"],
        },
    }


def test_run_hwp_accepts_complete_mock_readback_but_keeps_layout_review(run_context):
    state = run_context
    state.report = saved_report(state)
    result = execution.run_hwp(state.engine, state.job, state.folder)
    assert result["verified"] is True
    assert result["validation"]["field_readback"] == "passed"
    assert result["validation"]["layout_review"] == "required"
    assert result["worker_verification"] == state.report["verification"]
    assert result["warnings"] == []


@pytest.mark.parametrize("part", ["value", "hash"])
def test_run_hwp_rejects_inconsistent_readback_report(run_context, part):
    state = run_context
    state.report = saved_report(state)
    if part == "value":
        state.report["verification"]["readback"][0]["value"] = "Wrong notice"
    else:
        state.report["verification"]["output_sha256"] = "0" * 64
    with pytest.raises(WorkspaceError) as error:
        execution.run_hwp(state.engine, state.job, state.folder)
    assert error.value.detail["code"] == "worker_invalid_document"


def test_run_hwp_preserves_warning_draft_and_required_field_failures(run_context):
    state = run_context
    state.report = {
        "replaced": [],
        "missing": ["notice", "unmapped"],
        "remaining_placeholders": ["notice"],
    }
    result = execution.run_hwp(state.engine, state.job, state.folder)
    assert result["warnings"]
    assert result["required_missing"] == ["notice"]
    assert result["missing"] == ["notice", "unmapped"]
    assert result["remaining_placeholders"] == ["notice"]
    assert result["fields"] is None


@pytest.mark.parametrize("content", [None, b"", b"arbitrary nonempty output"])
def test_run_hwp_rejects_missing_or_invalid_artifact(run_context, content):
    state = run_context
    state.content = content
    with pytest.raises(WorkspaceError) as error:
        execution.run_hwp(state.engine, state.job, state.folder)
    assert error.value.status_code == 502
    assert error.value.detail["code"] == "worker_invalid_document"


@pytest.mark.parametrize(
    "report", [{"replaced": []}, {"error": "failure"}, {"replaced": ["other"]}]
)
def test_run_hwp_rechecks_provider_partition_and_errors(run_context, report):
    state = run_context
    state.report = report
    with pytest.raises(WorkspaceError) as error:
        execution.run_hwp(state.engine, state.job, state.folder)
    assert error.value.detail["code"] == "worker_invalid_response"


def test_required_inputs_still_block_before_worker(run_context):
    state = run_context
    state.preview["required_missing"] = ["notice"]
    with pytest.raises(WorkspaceError) as error:
        execution.run_hwp(state.engine, state.job, state.folder)
    assert error.value.detail["code"] == "required_missing"
    assert state.calls == 0


def test_stale_output_is_not_accepted_or_overwritten(run_context):
    state = run_context
    stale = state.folder / "draft.hwpx"
    stale.write_bytes(b"prior artifact")
    with pytest.raises(WorkspaceError) as error:
        execution.run_hwp(state.engine, state.job, state.folder)
    assert error.value.detail["code"] == "worker_output_exists"
    assert stale.read_bytes() == b"prior artifact"
    assert state.calls == 0


def test_mislabeled_template_is_blocked_before_com_write(run_context):
    state = run_context
    template = Path(state.preview["template"]["template_path"])
    template.write_bytes(hwp_bytes(compressed=True, trailer=True))
    state.content = template.read_bytes()
    with pytest.raises(WorkspaceError) as error:
        execution.run_hwp(state.engine, state.job, state.folder)
    assert error.value.detail["code"] == "template_path"
    assert state.calls == 0


def test_proposal_body_mapping_required_before_worker(run_context):
    state = run_context
    state.preview["template"]["kind"] = "proposal"
    state.preview["body_mapped"] = False
    with pytest.raises(WorkspaceError) as error:
        execution.run_hwp(state.engine, state.job, state.folder)
    assert error.value.detail["code"] == "proposal_body_unmapped"
    assert state.calls == 0


def test_missing_actual_template_fields_blocks_before_put_field(run_context, monkeypatch):
    state = run_context
    monkeypatch.setattr(execution, "inspect_template", lambda *args: {"inspection_passed": False})
    with pytest.raises(WorkspaceError) as error:
        execution.run_hwp(state.engine, state.job, state.folder)
    assert error.value.detail["code"] == "template_fields_missing"
    assert state.calls == 0


def test_hwpx_rejects_duplicate_archive_members():
    stream = io.BytesIO(hwpx_bytes())
    with zipfile.ZipFile(stream, "a") as archive, pytest.warns(UserWarning):
        archive.writestr("mimetype", "application/hwp+zip")
    with pytest.raises(HwpValidationError):
        validate_hwp_content(stream.getvalue(), ".hwpx")


def test_hwpx_rejects_damaged_member_crc():
    stream = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(hwpx_bytes())) as original,
        zipfile.ZipFile(stream, "w") as archive,
    ):
        for entry in original.infolist():
            archive.writestr(entry.filename, original.read(entry))
    content = stream.getvalue().replace(b"Draft content", b"Wrong content", 1)
    with pytest.raises(HwpValidationError):
        validate_hwp_content(content, ".hwpx")
