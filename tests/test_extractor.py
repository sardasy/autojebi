"""api/llm/extractor.py 단위 테스트 — 실제 Claude API 호출 없음.

abb-bid-pipeline의 tests/test_extractor.py에서 이식. patch 경로만
app.llm.extractor → api.llm.extractor 로 조정, pdf_bytes 인자 변경에 맞춰 PDF 케이스 정리.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from api.llm.extractor import extract_pdf_text, extract_specs
from api.llm.prompts import build_user_message
from api.llm.schemas import ElecSpec


class TestBuildUserMessage:
    def test_title_only(self) -> None:
        msg = build_user_message("ABB 변압기 구매", None, None)
        assert "ABB 변압기 구매" in msg
        assert "첨부" not in msg

    def test_includes_attachment_text(self) -> None:
        msg = build_user_message("ABB 변압기", "정격전압 22.9kV", None)
        assert "정격전압 22.9kV" in msg
        assert "첨부" in msg

    def test_truncates_long_attachment_text(self) -> None:
        long_text = "A" * 7000
        msg = build_user_message("제목", long_text, None)
        assert "이하 생략" in msg
        assert "A" * 6000 in msg

    def test_includes_raw_summary(self) -> None:
        msg = build_user_message("제목", None, "presmptPrce: 50000000")
        assert "presmptPrce" in msg


class TestElecSpec:
    def test_defaults_all_none(self) -> None:
        spec = ElecSpec()
        assert spec.product_category is None
        assert spec.standards == []

    def test_model_validate(self) -> None:
        data = {
            "product_category": "변압기",
            "quantity": 2,
            "rated_voltage_kv": 22.9,
            "rated_power_kva": 1000.0,
            "phases": 3,
            "cooling_type": "건식",
            "standards": ["KS C 4306"],
        }
        spec = ElecSpec.model_validate(data)
        assert spec.product_category == "변압기"
        assert spec.rated_voltage_kv == 22.9
        assert spec.standards == ["KS C 4306"]

    def test_dump_json_excludes_none(self) -> None:
        spec = ElecSpec(product_category="차단기", rated_voltage_kv=22.9)
        dumped = json.loads(spec.model_dump_json(exclude_none=True))
        assert "product_category" in dumped
        assert "quantity" not in dumped


class TestExtractPdfText:
    def test_extracts_text(self) -> None:
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "변압기 3상 22.9kV"
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "1,000kVA 건식"
        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page1, mock_page2]

        with patch("api.llm.extractor.pdfplumber.open", return_value=mock_pdf):
            text = extract_pdf_text(b"fake-pdf")

        assert "변압기 3상 22.9kV" in text
        assert "1,000kVA 건식" in text

    def test_skips_empty_pages(self) -> None:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = None
        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        with patch("api.llm.extractor.pdfplumber.open", return_value=mock_pdf):
            text = extract_pdf_text(b"fake-pdf")

        assert text == ""


def _make_tool_use_block(data: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_electrical_specs"
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


class TestExtractSpecs:
    def test_transformer_extraction(self) -> None:
        tool_result = {
            "product_category": "변압기",
            "quantity": 2,
            "rated_voltage_kv": 22.9,
            "rated_power_kva": 1000.0,
            "phases": 3,
            "cooling_type": "건식",
            "standards": ["KS C 4306"],
        }
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_mock_stream(tool_result)

        with patch("api.llm.extractor.anthropic.Anthropic", return_value=mock_client):
            spec = extract_specs("몰드변압기 구매 3상 22.9kV 1,000kVA")

        assert spec.product_category == "변압기"
        assert spec.rated_voltage_kv == 22.9
        assert spec.rated_power_kva == 1000.0
        assert spec.phases == 3
        assert "KS C 4306" in spec.standards

    def test_unrelated_bid_returns_empty_spec(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_mock_stream({})

        with patch("api.llm.extractor.anthropic.Anthropic", return_value=mock_client):
            spec = extract_specs("도로 포장 공사")

        assert spec.product_category is None
        assert spec.rated_voltage_kv is None

    def test_no_tool_use_block_returns_empty(self) -> None:
        message = MagicMock()
        message.content = []
        stream = MagicMock()
        stream.__enter__ = MagicMock(return_value=stream)
        stream.__exit__ = MagicMock(return_value=False)
        stream.get_final_message = MagicMock(return_value=message)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = stream

        with patch("api.llm.extractor.anthropic.Anthropic", return_value=mock_client):
            spec = extract_specs("변압기 구매")

        assert spec == ElecSpec()

    def test_attachment_text_passed_to_user_message(self) -> None:
        tool_result = {"product_category": "인버터", "rated_power_kw": 75.0}
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_mock_stream(tool_result)

        with patch("api.llm.extractor.anthropic.Anthropic", return_value=mock_client):
            spec = extract_specs(
                "인버터 구매",
                attachment_text="75kW 인버터 IP54",
                raw_json_summary="bidNtceNm: 인버터 구매",
            )

        assert spec.product_category == "인버터"
        call_kwargs = mock_client.messages.stream.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "75kW 인버터 IP54" in user_content
        assert "bidNtceNm" in user_content

    def test_uses_settings_model_and_max_tokens(self) -> None:
        from api.config import settings as cfg

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _make_mock_stream({})

        with patch("api.llm.extractor.anthropic.Anthropic", return_value=mock_client):
            extract_specs("아무 제목")

        call_kwargs = mock_client.messages.stream.call_args.kwargs
        assert call_kwargs["model"] == cfg.anthropic_model
        assert call_kwargs["max_tokens"] == cfg.anthropic_max_tokens
        # cache_control이 system 메시지에 붙어있는지
        assert call_kwargs["system"][0]["cache_control"]["type"] == "ephemeral"
