"""Hermetic G2B attachment inventory and inert original upload/extraction regressions."""

from __future__ import annotations

import copy
import hashlib
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from api.config import Settings, settings
from api.services import uploads
from api.services.g2b_attachments import iter_g2b_attachments
from api.workspace import execution
from api.workspace.errors import WorkspaceError

OLE = bytes.fromhex("d0cf11e0a1b11ae1")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(
        settings, "upload_allowed_exts", Settings.model_fields["upload_allowed_exts"].default
    )
    monkeypatch.setattr(settings, "upload_max_bytes", 50_000)
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("HWP_AGENT_TOKEN", "test-only-token-to-exercise-ole-routing")
    monkeypatch.setattr(
        execution, "HwpAgentClient", lambda *args, **kwargs: pytest.fail("unexpected HWP call")
    )


@pytest.fixture
def transport(monkeypatch):
    responses, requests = {}, []
    original = httpx.Client

    def handle(request):
        url = str(request.url)
        requests.append(url)
        assert url in responses, "unexpected HTTP request in hermetic test"
        status, content = responses[url]
        return httpx.Response(
            status, content=content, headers={"Location": "http://127.0.0.1/private"}
        )

    mock = httpx.MockTransport(handle)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=mock, **kwargs))
    return SimpleNamespace(responses=responses, requests=requests)


def job_for(transport, files, documents=None):
    raw = {}
    for index, name, content in files:
        url = f"https://www.g2b.go.kr/attachment?id={index}"
        raw[f"ntceSpecDocUrl{index}"] = url
        raw[f"ntceSpecFileNm{index}"] = name
        transport.responses[url] = (200, content)
    return {"notice_no": "FETCH-TEST", "snapshot": {"raw": raw, "documents": documents or []}}


def test_legacy_iterator_stays_filtered_but_inventory_includes_all_slots():
    raw = {
        "ntceSpecFileNm1": "one.pdf",
        "ntceSpecDocUrl1": "https://example.test/1",
        "ntceSpecFileNm2": "sheet.xls",
        "ntceSpecDocUrl2": "https://example.test/2",
        "ntceSpecFileNm3": "missing-url.hwp",
        "ntceSpecDocUrl4": "https://example.test/4",
        "ntceSpecFileNm5": "",
        "ntceSpecDocUrl5": "",
        "ntceSpecDocNm6": "alternate-name.hwp",
        "ntceSpecDocUrl6": "https://example.test/6",
        "ntceSpecFileNm11": "last.unknown",
        "ntceSpecDocUrl11": "https://example.test/11",
    }
    assert [item.index for item in iter_g2b_attachments(raw)] == [1]
    items = iter_g2b_attachments(raw, include_unsupported=True)
    assert [item.index for item in items] == [1, 2, 3, 4, 6, 11]
    assert items[2].url == "" and items[3].filename == "g2b-attachment-4.bin"
    assert items[4].filename == "alternate-name.hwp"


def test_four_declared_files_include_inert_xls_and_exact_references(transport):
    files = [
        (1, "notice.pdf", b"pdf"),
        (2, "spec.hwp", OLE + b"hwp"),
        (3, "form.hwpx", b"hwpx"),
        (4, "software.xls", OLE + b"xls"),
    ]
    job = job_for(transport, files)
    result = execution.fetch_sources(job)
    assert "xls" in settings.upload_allowed_ext_set
    assert len(result["documents"]) == len(result["source_inventory"]) == 4
    assert result["warnings"] == []
    for (index, name, content), doc, item in zip(
        files, result["documents"], result["source_inventory"], strict=True
    ):
        url = job["snapshot"]["raw"][f"ntceSpecDocUrl{index}"]
        assert doc["attachment_index"] == index and doc["attachment_url"] == url
        assert doc["role"] == "notice_source" and doc["confirmed"] is False
        assert Path(doc["storage_path"]).read_bytes() == content
        assert item == {
            "index": index,
            "name": name,
            "url": url,
            "status": "downloaded",
            "reason": "downloaded",
            "document_id": doc["id"],
            "sha256": doc["sha256"],
        }
    assert Path(result["documents"][3]["storage_path"]).suffix == ".xls"


def test_unknown_extension_warns_without_losing_slot(transport):
    with pytest.raises(WorkspaceError) as error:
        execution.fetch_sources(job_for(transport, [(1, "spec.unknown", b"inert")]))
    assert error.value.status_code == 502
    result = error.value.detail
    assert result["code"] == "attachment_fetch_failed" and len(result["warnings"]) == 1
    item = result["source_inventory"][0]
    assert item["status"] == "unsupported" and item["reason"] == "unsupported_extension"
    assert item["index"] == 1 and item["document_id"] is None


def test_save_stream_415_is_accounted_and_sanitized(transport, monkeypatch):
    def unsupported(*args, **kwargs):
        raise uploads.UploadError(415, "SECRET unsupported provider details")

    monkeypatch.setattr(uploads, "save_stream", unsupported)
    with pytest.raises(WorkspaceError) as error:
        execution.fetch_sources(job_for(transport, [(1, "spec.pdf", b"data")]))
    assert error.value.status_code == 502
    result = error.value.detail
    assert result["source_inventory"][0]["status"] == "unsupported"
    assert result["warnings"] and "SECRET" not in str(result)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://127.0.0.1/private",
        "https://evil.test/file",
        "https://g2b.go.kr:bad/file",
        "https://[invalid/file",
        "https://user:password@g2b.go.kr/file",
        "data:text/plain,raw",
    ],
)
def test_missing_or_invalid_url_warns_and_does_not_block_later_slots(transport, url):
    job = job_for(transport, [(2, "good.pdf", b"good")])
    job["snapshot"]["raw"].update(ntceSpecFileNm1="bad.xls", ntceSpecDocUrl1=url)
    result = execution.fetch_sources(job)
    assert len(result["documents"]) == 1 and len(result["warnings"]) == 1
    first, second = result["source_inventory"]
    assert first["status"] == "failed"
    assert first["reason"] == ("missing_url" if not url else "invalid_url")
    assert first["url"] == url and second["status"] == "downloaded"
    assert transport.requests == [job["snapshot"]["raw"]["ntceSpecDocUrl2"]]


@pytest.mark.parametrize("raw", [{}, {"ntceSpecFileNm1": "", "ntceSpecDocUrl1": ""}, None])
def test_empty_declared_inventory_is_not_a_clean_result(transport, raw):
    result = execution.fetch_sources(
        {"notice_no": "FETCH-TEST", "snapshot": {"raw": raw, "documents": []}}
    )
    assert result["documents"] == result["source_inventory"] == []
    assert result["warnings"] and not transport.requests


def test_same_slot_url_hash_reuses_id_and_preserves_manual_metadata(transport):
    job = job_for(transport, [(1, "spec.pdf", b"same")])
    original = execution.fetch_sources(job)["documents"][0]
    original.update(
        name="manual name.pdf",
        text="manually confirmed text",
        text_origin="manual_confirmed",
        confirmed=True,
        custom_review={"note": "keep"},
    )
    before = copy.deepcopy(original)
    job["snapshot"]["documents"] = [original]
    result = execution.fetch_sources(job)
    assert result["documents"] == [before] and original == before
    assert result["source_inventory"][0]["document_id"] == original["id"]
    assert result["source_inventory"][0]["reason"] == "same_attachment_hash"
    assert result["warnings"] == []


def test_identical_bytes_at_two_indices_get_distinct_ids_and_keep_them_on_rerun(transport):
    job = job_for(transport, [(1, "first.pdf", b"same"), (2, "second.pdf", b"same")])
    first = execution.fetch_sources(job)
    one, two = first["documents"]
    assert one["id"] != two["id"] and one["storage_path"] == two["storage_path"]
    assert [doc["attachment_index"] for doc in first["documents"]] == [1, 2]
    assert [item["status"] for item in first["source_inventory"]] == ["downloaded", "duplicate"]
    job["snapshot"]["documents"] = list(reversed(first["documents"]))
    again = execution.fetch_sources(job)
    assert [doc["id"] for doc in again["documents"]] == [one["id"], two["id"]]
    assert [item["document_id"] for item in again["source_inventory"]] == [one["id"], two["id"]]
    assert all(item["reason"] == "same_attachment_hash" for item in again["source_inventory"])


def test_legacy_notice_hash_gets_new_id_with_manual_text_preserved(transport):
    job = job_for(transport, [(1, "spec.pdf", b"same")])
    legacy = execution.fetch_sources(job)["documents"][0]
    legacy.pop("attachment_index")
    legacy.pop("attachment_url")
    legacy.update(confirmed=True, text="manual body", text_origin="manual_confirmed")
    before = copy.deepcopy(legacy)
    job["snapshot"]["documents"] = [legacy]
    result = execution.fetch_sources(job)
    doc = result["documents"][0]
    assert doc["id"] != legacy["id"] and doc["storage_path"] == legacy["storage_path"]
    assert doc["confirmed"] is False and doc["text"] == "manual body"
    assert doc["text_origin"] == "manual_confirmed"
    assert doc["attachment_index"] == 1 and legacy == before
    assert result["source_inventory"][0]["document_id"] == doc["id"]


def test_matching_company_evidence_is_not_reclassified_or_linked(transport):
    job = job_for(transport, [(1, "spec.pdf", b"same")])
    company = execution.fetch_sources(job)["documents"][0]
    company.update(role="company_evidence", confirmed=True, text="company secret text")
    before = copy.deepcopy(company)
    job["snapshot"]["documents"] = [company]
    result = execution.fetch_sources(job)
    doc = result["documents"][0]
    assert doc["id"] != company["id"] and doc["storage_path"] != company["storage_path"]
    assert doc["role"] == "notice_source" and doc["confirmed"] is False and doc["text"] == ""
    assert result["source_inventory"][0]["status"] == "downloaded" and company == before


@pytest.mark.parametrize("change", ["url", "hash", "missing-file"])
def test_changed_attachment_or_missing_original_does_not_reuse_id(transport, change):
    job = job_for(transport, [(1, "spec.pdf", b"same")])
    original = execution.fetch_sources(job)["documents"][0]
    job["snapshot"]["documents"] = [original]
    if change == "url":
        new_url = "https://g2b.go.kr/changed"
        job["snapshot"]["raw"]["ntceSpecDocUrl1"] = new_url
        transport.responses[new_url] = (200, b"same")
    elif change == "hash":
        transport.responses[original["attachment_url"]] = (200, b"changed")
    else:
        Path(original["storage_path"]).unlink()
    result = execution.fetch_sources(job)
    assert result["documents"][0]["id"] != original["id"]
    assert result["source_inventory"][0]["status"] == (
        "duplicate" if change == "url" else "downloaded"
    )


@pytest.mark.parametrize("status,content", [(404, b"error"), (302, b"redirect"), (200, b"")])
def test_failed_download_keeps_slot_inventory(transport, status, content):
    job = job_for(transport, [(1, "bad.pdf", b"first"), (2, "good.pdf", b"good")])
    transport.responses[job["snapshot"]["raw"]["ntceSpecDocUrl1"]] = (status, content)
    result = execution.fetch_sources(job)
    assert [item["status"] for item in result["source_inventory"]] == ["failed", "downloaded"]
    assert result["warnings"] and len(result["documents"]) == 1
    assert len(transport.requests) == 2


@pytest.mark.parametrize("failure", ["http", "transport", "missing-url", "invalid-url"])
def test_all_declared_attachments_failed_remain_http_502_with_inventory(
    transport, monkeypatch, failure
):
    from api.workspace.worker import http_failure

    job = job_for(transport, [(1, "one.pdf", b"first"), (2, "two.xls", b"second")])
    raw = job["snapshot"]["raw"]
    if failure == "transport":

        class OfflineClient:
            def __enter__(self):
                raise httpx.ConnectError("SECRET transport details")

            def __exit__(self, *args):
                pass

        monkeypatch.setattr(httpx, "Client", lambda **kwargs: OfflineClient())
        monkeypatch.setattr("tenacity.nap.time.sleep", lambda _: None)
    for index in (1, 2):
        if failure == "missing-url":
            raw[f"ntceSpecDocUrl{index}"] = ""
        elif failure == "invalid-url":
            raw[f"ntceSpecDocUrl{index}"] = "https://evil.test/file"
        elif failure == "http":
            transport.responses[raw[f"ntceSpecDocUrl{index}"]] = (503, b"unavailable")
    with pytest.raises(WorkspaceError) as error:
        execution.fetch_sources(job)
    assert error.value.status_code == 502
    detail = error.value.detail
    assert detail["code"] == "attachment_fetch_failed" and detail["job_id"] is None
    assert [item["index"] for item in detail["source_inventory"]] == [1, 2]
    assert all(item["status"] == "failed" for item in detail["source_inventory"])
    assert len(detail["warnings"]) == 2 and "SECRET" not in str(detail)
    status, persisted_error = http_failure(error.value)
    assert status == "failed" and persisted_error is detail


def test_partial_unknown_extension_warns_but_keeps_successful_download(transport):
    job = job_for(transport, [(1, "unknown.bin", b"unknown"), (2, "good.xls", OLE + b"xls")])
    result = execution.fetch_sources(job)
    assert len(result["documents"]) == 1 and result["documents"][0]["attachment_index"] == 2
    assert [item["status"] for item in result["source_inventory"]] == ["unsupported", "downloaded"]
    assert len(result["warnings"]) == 1


def test_new_index_with_same_hash_does_not_inherit_source_confirmation(transport):
    job = job_for(transport, [(1, "first.pdf", b"same")])
    original = execution.fetch_sources(job)["documents"][0]
    original.update(confirmed=True, text="manual source text", text_origin="manual_confirmed")
    before = copy.deepcopy(original)
    second = job_for(transport, [(2, "second.pdf", b"same")], documents=[original])
    result = execution.fetch_sources(second)
    doc = result["documents"][0]
    assert doc["id"] != original["id"] and doc["confirmed"] is False
    assert doc["text"] == original["text"] and doc["storage_path"] == original["storage_path"]
    assert original == before


@pytest.mark.parametrize("extension", ["xls", "doc", "ppt"])
def test_non_hwp_ole_is_never_sent_to_hwp_worker(tmp_path, extension):
    path = Path(settings.upload_dir) / f"original.{extension}"
    path.parent.mkdir()
    content = OLE + b"inert spreadsheet/document"
    path.write_bytes(content)
    unsupported = {
        "id": "ole",
        "name": path.name,
        "storage_path": str(path),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    manual = {
        "id": "manual",
        "name": "confirmed.pdf",
        "text": "manual text",
        "text_origin": "manual_confirmed",
    }
    result = execution.extract({"snapshot": {"documents": [unsupported, manual]}})
    assert result["documents"] == [
        {"id": "manual", "text": "manual text", "format": "manual_confirmed"}
    ]
    assert len(result["warnings"]) == 1 and path.name in result["warnings"][0]
    with pytest.raises(WorkspaceError) as error:
        execution.extract({"snapshot": {"documents": [unsupported]}})
    assert error.value.detail["code"] == "no_extracted_text"


def test_xls_named_document_sharing_hwp_storage_still_does_not_call_hwp(tmp_path):
    path = Path(settings.upload_dir) / "shared.hwp"
    path.parent.mkdir()
    path.write_bytes(OLE + b"same bytes")
    with pytest.raises(WorkspaceError) as error:
        execution.extract(
            {
                "snapshot": {
                    "documents": [{"id": "xls", "name": "sheet.xls", "storage_path": str(path)}]
                }
            }
        )
    assert error.value.detail["code"] == "no_extracted_text"


def test_hwp_ole_still_uses_worker_when_suffix_matches(tmp_path, monkeypatch):
    path = Path(settings.upload_dir) / "original.HWP"
    path.parent.mkdir()
    path.write_bytes(OLE + b"hwp document")
    calls = []
    monkeypatch.setattr(
        execution,
        "HwpAgentClient",
        lambda **kwargs: SimpleNamespace(
            analyze_document=lambda value: calls.append(value) or {"text": "HWP body"},
        ),
    )
    result = execution.extract(
        {
            "snapshot": {
                "documents": [{"id": "hwp", "name": "original.HWP", "storage_path": str(path)}]
            }
        }
    )
    extracted = result["documents"][0]
    assert {key: extracted[key] for key in ("id", "text", "format")} == {
        "id": "hwp", "text": "HWP body", "format": "hwp_ole",
    }
    assert extracted["extraction"]["tables"] == []
    assert extracted["extraction"]["table_structure"]["status"] == "unknown"
    assert not extracted["extraction"]["table_structure"]["needs_review"]
    assert calls == [str(path)] and not result["warnings"]


def section_archive() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("Contents/section0.xml", "<section><text>HWPX body</text></section>")
    return stream.getvalue()


def test_zip_original_is_stored_untouched_without_opening_archive(transport, monkeypatch):
    content = section_archive()
    original_zip = zipfile.ZipFile
    monkeypatch.setattr(
        execution.zipfile, "ZipFile", lambda *args, **kwargs: pytest.fail("ZIP must stay inert")
    )
    result = execution.fetch_sources(job_for(transport, [(3, "original.zip", content)]))
    assert "zip" in settings.upload_allowed_ext_set
    assert result["warnings"] == []
    doc = result["documents"][0]
    assert doc["attachment_index"] == 3 and doc["confirmed"] is False
    assert doc["text"] == "" and doc["text_origin"] == "unread"
    path = Path(doc["storage_path"])
    assert path.suffix == ".zip" and path.read_bytes() == content
    assert doc["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["source_inventory"][0]["status"] == "downloaded"
    monkeypatch.setattr(execution.zipfile, "ZipFile", original_zip)
    extracted = execution.extract({"snapshot": {"documents": [doc]}})
    assert extracted["documents"][0]["text"] == ""
    assert not extracted["documents"][0]["extraction"]["complete"]
    assert extracted["documents"][0]["extraction"]["members"][0]["status"] == "unsupported"
    assert path.read_bytes() == content
    assert not list(path.parent.rglob("*.xml"))


@pytest.mark.parametrize(
    "name,stored_name",
    [
        ("original.zip", "shared.hwpx"),
        ("sheet.xlsx", "shared.hwpx"),
        ("declared.hwpx", "shared.zip"),
        ("declared.hwpx", "shared.xlsx"),
        ("", "shared.hwpx"),
    ],
)
def test_non_hwpx_pk_and_cross_extension_aliases_are_not_parsed(
    monkeypatch, name, stored_name
):
    content = section_archive()
    path = Path(settings.upload_dir) / stored_name
    path.parent.mkdir()
    path.write_bytes(content)
    opened = []
    original_zip_file = zipfile.ZipFile

    def tracked_zip_file(*args, **kwargs):
        opened.append(args)
        return original_zip_file(*args, **kwargs)

    monkeypatch.setattr(execution.zipfile, "ZipFile", tracked_zip_file)
    doc = {"id": "archive", "name": name, "storage_path": str(path)}
    manual = {"id": "manual", "text": "checked text", "text_origin": "manual_confirmed"}
    result = execution.extract({"snapshot": {"documents": [doc, manual]}})
    assert result["documents"] == [
        {"id": "manual", "text": "checked text", "format": "manual_confirmed"}
    ]
    assert len(result["warnings"]) == 1
    assert opened == [] and path.read_bytes() == content


@pytest.mark.parametrize("extension", ["hwpx", "HWPX"])
def test_hwpx_sections_still_extract_when_both_extensions_match(extension):
    path = Path(settings.upload_dir) / f"original.{extension}"
    path.parent.mkdir()
    path.write_bytes(section_archive())
    doc = {"id": "hwpx", "name": f"declared.{extension}", "storage_path": str(path)}
    result = execution.extract({"snapshot": {"documents": [doc]}})
    extracted = result["documents"][0]
    assert {key: extracted[key] for key in ("id", "text", "format")} == {
        "id": "hwpx", "text": "HWPX body", "format": "hwpx",
    }
    assert extracted["extraction"]["tables"] == []
    assert extracted["extraction"]["table_structure"]["status"] == "not_detected"
    assert not extracted["extraction"]["table_structure"]["needs_review"]
    assert result["warnings"] == []
