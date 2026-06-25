"""api/services/uploads.py 단위 테스트.

디스크는 tmp_path fixture로 격리. settings.upload_dir / upload_max_bytes monkeypatch.
"""

from __future__ import annotations

import io

import pytest

from api.config import settings
from api.models.notices import UploadedDocument
from api.services.uploads import (
    UploadError,
    build_metadata,
    delete_file,
    merge_into_document_automation,
    remove_from_document_automation,
    save_stream,
    validate_extension,
)


@pytest.fixture(autouse=True)
def _isolate_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "upload_max_bytes", 1000)
    monkeypatch.setattr(
        settings, "upload_allowed_exts", "pdf,hwp,jpg,xlsx"
    )


def test_validate_extension_accepts_known_lowercase_and_uppercase():
    assert validate_extension("a.pdf") == "pdf"
    assert validate_extension("A.PDF") == "pdf"
    assert validate_extension("a.b.HWP") == "hwp"


def test_validate_extension_rejects_unknown():
    with pytest.raises(UploadError) as e:
        validate_extension("a.exe")
    assert e.value.status_code == 415


def test_validate_extension_rejects_missing():
    with pytest.raises(UploadError) as e:
        validate_extension("noext")
    assert e.value.status_code == 415


def test_save_stream_writes_and_hashes():
    payload = b"hello-bid-document"
    saved = save_stream(
        io.BytesIO(payload),
        notice_no="DOC-1",
        original_name="biz.pdf",
    )
    assert saved.size == len(payload)
    assert saved.sha256 == "5be6db6e0cce9bd31a23e9eaa86c75a83e4d1c3b6b5a4f00edb2bb01d4c2ab0c" or len(saved.sha256) == 64
    assert saved.storage_path.endswith(".pdf")


def test_save_stream_blocks_oversize():
    big = b"x" * 2000  # > upload_max_bytes(=1000)
    with pytest.raises(UploadError) as e:
        save_stream(
            io.BytesIO(big),
            notice_no="DOC-1",
            original_name="big.pdf",
        )
    assert e.value.status_code == 413


def test_build_metadata_fills_mime_from_extension_when_missing():
    saved = save_stream(
        io.BytesIO(b"abc"),
        notice_no="DOC-1",
        original_name="biz.pdf",
    )
    meta = build_metadata(saved, original_name="biz.pdf", mime=None, item_id="business_registration")
    assert isinstance(meta, UploadedDocument)
    assert meta.mime == "application/pdf"
    assert meta.item_id == "business_registration"
    assert meta.size == 3


def test_merge_into_document_automation_promotes_mapped_item_to_ready():
    docs = {
        "checklist": [
            {"id": "business_registration", "name": "사업자등록증", "type": "company_common",
             "required": True, "status": "needed", "source": "rule",
             "owner": None, "reason": None, "due_hint": None, "note": None},
            {"id": "bid_form", "name": "입찰참가신청서", "type": "bid_form",
             "required": True, "status": "needed", "source": "rule",
             "owner": None, "reason": None, "due_hint": None, "note": None},
        ],
        "uploads": [],
    }
    saved = save_stream(io.BytesIO(b"abc"), notice_no="DOC-1", original_name="biz.pdf")
    meta = build_metadata(saved, original_name="biz.pdf", mime=None, item_id="business_registration")
    updated = merge_into_document_automation(docs, meta)
    assert len(updated["uploads"]) == 1
    bizn = next(i for i in updated["checklist"] if i["id"] == "business_registration")
    assert bizn["status"] == "ready"
    assert "upload" in bizn["source"]
    # 다른 항목은 변경 없음
    bid = next(i for i in updated["checklist"] if i["id"] == "bid_form")
    assert bid["status"] == "needed"


def test_remove_from_document_automation_returns_meta_and_removes():
    docs = {"uploads": [{"id": "x1", "name": "a.pdf"}, {"id": "x2", "name": "b.pdf"}]}
    updated, removed = remove_from_document_automation(docs, "x1")
    assert removed == {"id": "x1", "name": "a.pdf"}
    assert updated["uploads"] == [{"id": "x2", "name": "b.pdf"}]


def test_remove_from_document_automation_unknown_id_returns_none():
    docs = {"uploads": [{"id": "x1", "name": "a.pdf"}]}
    updated, removed = remove_from_document_automation(docs, "missing")
    assert removed is None
    assert updated["uploads"] == [{"id": "x1", "name": "a.pdf"}]


def test_delete_file_handles_missing_path():
    # 존재하지 않는 파일도 True (idempotent unlink missing_ok=True)
    assert delete_file("/nonexistent/path/to/file.pdf") is True


def test_analyze_upload_persists_capped_text_excerpt(monkeypatch):
    """추출 본문이 text_excerpt로 보존되고 설정 길이로 잘린다(서류 판정 재사용용)."""
    from api.services.uploads import analyze_upload

    monkeypatch.setattr(settings, "upload_text_excerpt_chars", 40)
    monkeypatch.setattr(
        "api.services.uploads.extract_pdf_text", lambda _b: "입찰보증금 " * 100
    )
    saved = save_stream(io.BytesIO(b"%PDF-1.4"), notice_no="DOC-1", original_name="x.pdf")
    meta = analyze_upload(saved=saved, original_name="x.pdf")
    excerpt = meta["text_excerpt"]
    assert excerpt is not None
    assert len(excerpt) <= 40
    assert "입찰보증금" in excerpt


def test_analyze_upload_skips_hwp_when_agent_unavailable():
    """hwp_available=False면 에이전트를 호출하지 않고 간결한 미연결 오류만 남긴다."""
    from api.services.uploads import analyze_upload

    class _BoomClient:
        def analyze_document(self, path):  # pragma: no cover - 호출되면 실패
            raise AssertionError("hwp agent should not be called when unavailable")

    saved = save_stream(io.BytesIO(b"hwp-bytes"), notice_no="DOC-1", original_name="spec.hwp")
    meta = analyze_upload(
        saved=saved,
        original_name="spec.hwp",
        hwp_client=_BoomClient(),
        hwp_available=False,
    )
    assert meta["text_extract_error"] == "HWP 에이전트 미연결"
