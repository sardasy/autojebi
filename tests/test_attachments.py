"""api/services/attachments.py 단위 테스트.

다운로드는 `_download` 헬퍼를 직접 패치해 디스크에 바이트를 쓰는 방식으로 격리.
(httpx.Client 자체를 mock하면 fake_client 내부에서 httpx.Client를 다시 부르며
재귀 호출되는 함정이 있음.) HWP 처리는 HwpAgentClient mock으로 주입.

어떤 단계든 실패하면 None을 반환해야 함 (호출자 ClaudeAnalyzer 보호 계약).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.services import attachments


@pytest.fixture
def temp_attachment_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(attachments.settings, "g2b_attachment_dir", str(tmp_path))
    return tmp_path


def _successful_download(content: bytes):
    """_download 패치용: 호출되면 dest에 content를 쓰고 True 반환."""

    def fake_download(url: str, dest: Path) -> bool:
        dest.write_bytes(content)
        return True

    return fake_download


def test_returns_none_when_raw_empty():
    assert attachments.fetch_first_attachment_text(None) is None
    assert attachments.fetch_first_attachment_text({}) is None


def test_returns_none_when_url_missing():
    raw = {"ntceSpecDocUrl1": "", "ntceSpecFileNm1": "x.hwp"}
    assert attachments.fetch_first_attachment_text(raw) is None


def test_returns_none_when_filename_missing():
    raw = {"ntceSpecDocUrl1": "https://x.test/a", "ntceSpecFileNm1": ""}
    assert attachments.fetch_first_attachment_text(raw) is None


def test_returns_none_for_unsupported_extension(temp_attachment_dir):
    raw = {
        "ntceSpecDocUrl1": "https://x.test/a.zip",
        "ntceSpecFileNm1": "spec.zip",
    }
    assert attachments.fetch_first_attachment_text(raw) is None


def test_pdf_path_calls_extract_pdf_text(temp_attachment_dir):
    raw = {
        "ntceSpecDocUrl1": "https://x.test/a.pdf",
        "ntceSpecFileNm1": "spec.pdf",
    }

    with (
        patch.object(attachments, "_download", side_effect=_successful_download(b"%PDF")),
        patch(
            "api.services.attachments.extract_pdf_text",
            return_value="추출된 PDF 본문",
        ) as mock_extract,
    ):
        text = attachments.fetch_first_attachment_text(raw)

    assert text == "추출된 PDF 본문"
    mock_extract.assert_called_once()


def test_hwp_path_uses_text_key_from_agent_response(temp_attachment_dir):
    raw = {
        "ntceSpecDocUrl1": "https://x.test/a.hwp",
        "ntceSpecFileNm1": "spec.hwp",
    }
    hwp_client = MagicMock()
    hwp_client.analyze_document.return_value = {"text": "HWP 본문 텍스트"}

    with patch.object(attachments, "_download", side_effect=_successful_download(b"HWP")):
        text = attachments.fetch_first_attachment_text(raw, hwp_client=hwp_client)

    assert text == "HWP 본문 텍스트"
    hwp_client.analyze_document.assert_called_once()


def test_hwp_path_falls_back_to_json_when_no_body_key(temp_attachment_dir):
    """현재 milim-hwp-agent의 analyze_document는 placeholder 탐지용이라
    본문 텍스트 키가 없을 수 있음. 그 경우 응답을 JSON으로 직렬화해 약신호로 사용."""
    raw = {
        "ntceSpecDocUrl1": "https://x.test/a.hwp",
        "ntceSpecFileNm1": "spec.hwp",
    }
    hwp_client = MagicMock()
    hwp_client.analyze_document.return_value = {
        "placeholders": ["{{company_name}}"],
        "stats": {"placeholders": 1},
    }

    with patch.object(attachments, "_download", side_effect=_successful_download(b"HWP")):
        text = attachments.fetch_first_attachment_text(raw, hwp_client=hwp_client)

    assert text is not None
    assert "placeholders" in text  # JSON 직렬화 약신호


def test_download_failure_returns_none(temp_attachment_dir):
    raw = {
        "ntceSpecDocUrl1": "https://x.test/a.pdf",
        "ntceSpecFileNm1": "spec.pdf",
    }

    with patch.object(attachments, "_download", return_value=False):
        text = attachments.fetch_first_attachment_text(raw)

    assert text is None


def test_pdf_extraction_failure_returns_none(temp_attachment_dir):
    raw = {
        "ntceSpecDocUrl1": "https://x.test/a.pdf",
        "ntceSpecFileNm1": "spec.pdf",
    }

    with (
        patch.object(attachments, "_download", side_effect=_successful_download(b"corrupt")),
        patch(
            "api.services.attachments.extract_pdf_text",
            side_effect=Exception("corrupt pdf"),
        ),
    ):
        text = attachments.fetch_first_attachment_text(raw)

    assert text is None


def test_hwp_agent_error_returns_none(temp_attachment_dir):
    """HwpAgentError가 발생해도 None 반환 (raise 금지 계약)."""
    raw = {
        "ntceSpecDocUrl1": "https://x.test/a.hwp",
        "ntceSpecFileNm1": "spec.hwp",
    }
    from api.services.hwp_agent_client import HwpAgentError

    hwp_client = MagicMock()
    hwp_client.analyze_document.side_effect = HwpAgentError("agent down")

    with patch.object(attachments, "_download", side_effect=_successful_download(b"HWP")):
        text = attachments.fetch_first_attachment_text(raw, hwp_client=hwp_client)

    assert text is None
