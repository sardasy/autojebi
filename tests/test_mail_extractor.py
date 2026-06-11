"""api/services/mail_extractor.py 단위 테스트 — 실제 Claude API 호출 없음."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from api.llm.mail_schemas import KjebiMailExtraction
from api.services.mail_extractor import extract_notice_from_mail


def _make_tool_use_block(data: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_notice_from_mail"
    block.input = data
    return block


def _make_mock_stream(tool_input: dict) -> MagicMock:
    message = MagicMock()
    message.content = [_make_tool_use_block(tool_input)]
    stream = MagicMock()
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)
    stream.get_final_message = MagicMock(return_value=message)
    return stream


class TestExtractNoticeFromMail:
    def test_full_extraction_returns_high_confidence(self) -> None:
        tool_result = {
            "notice_no": "R26BK01543282-000",
            "title": "22.9kV 몰드변압기 구매",
            "org_name": "한국전력공사 경기지역본부",
            "close_date": "2026-06-20T18:00:00+09:00",
            "base_price": 78000000.0,
            "bid_url": "https://www.g2b.go.kr/pt/menu/main.do?vno=R26BK01543282",
            "summary": "22.9kV 몰드변압기 구매 공고",
        }
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_mock_stream(tool_result)

        with patch("api.services.mail_extractor.settings.anthropic_api_key", "sk-test"), patch(
            "api.services.mail_extractor.anthropic.Anthropic", return_value=mock_client
        ):
            result = extract_notice_from_mail("□ 공고번호 : R26BK01543282-000 ...")

        assert result.extracted.notice_no == "R26BK01543282-000"
        assert result.extracted.base_price == 78000000.0
        # 7 / 7 fields filled → 1.0
        assert result.confidence == 1.0
        assert result.errors == []

    def test_partial_extraction_lower_confidence(self) -> None:
        tool_result = {
            "notice_no": "R26AB99988877-000",
            "title": "차단기 구매 공고",
            "close_date": "2026-07-05T18:00:00+09:00",
            "summary": "차단기 구매",
        }
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_mock_stream(tool_result)

        with patch("api.services.mail_extractor.settings.anthropic_api_key", "sk-test"), patch(
            "api.services.mail_extractor.anthropic.Anthropic", return_value=mock_client
        ):
            result = extract_notice_from_mail("차단기 구매 공고 — R26AB99988877-000 / 2026.07.05")

        assert result.extracted.notice_no == "R26AB99988877-000"
        assert result.extracted.org_name is None
        # 4 / 7 fields ≈ 0.571
        assert 0.4 < result.confidence < 0.7

    def test_missing_notice_no_returns_zero_confidence(self) -> None:
        tool_result = {"title": "어디서 왔는지 모를 공고"}
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_mock_stream(tool_result)

        with patch("api.services.mail_extractor.settings.anthropic_api_key", "sk-test"), patch(
            "api.services.mail_extractor.anthropic.Anthropic", return_value=mock_client
        ):
            result = extract_notice_from_mail("notice_no 없는 본문")

        assert result.extracted.notice_no is None
        assert result.confidence == 0.0
        assert result.errors == []

    def test_empty_input_returns_empty_extraction(self) -> None:
        result = extract_notice_from_mail("   ")
        assert result.extracted == KjebiMailExtraction()
        assert result.confidence == 0.0
        assert result.errors == ["empty input"]

    def test_no_api_key_short_circuits(self) -> None:
        with patch("api.services.mail_extractor.settings.anthropic_api_key", ""):
            result = extract_notice_from_mail("□ 공고번호 : R26-000")
        assert result.confidence == 0.0
        assert any("ANTHROPIC_API_KEY" in e for e in result.errors)

    def test_claude_call_failure_returns_errors(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = RuntimeError("rate limited")

        with patch("api.services.mail_extractor.settings.anthropic_api_key", "sk-test"), patch(
            "api.services.mail_extractor.anthropic.Anthropic", return_value=mock_client
        ):
            result = extract_notice_from_mail("□ 공고번호 : R26-000")

        assert result.confidence == 0.0
        assert any("claude error" in e for e in result.errors)

    def test_no_tool_use_block_returns_empty(self) -> None:
        message = MagicMock()
        message.content = []
        stream = MagicMock()
        stream.__enter__ = MagicMock(return_value=stream)
        stream.__exit__ = MagicMock(return_value=False)
        stream.get_final_message = MagicMock(return_value=message)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = stream

        with patch("api.services.mail_extractor.settings.anthropic_api_key", "sk-test"), patch(
            "api.services.mail_extractor.anthropic.Anthropic", return_value=mock_client
        ):
            result = extract_notice_from_mail("□ 공고번호 : R26-000")

        assert result.extracted == KjebiMailExtraction()
        assert result.confidence == 0.0
        assert "no tool_use block" in result.errors
