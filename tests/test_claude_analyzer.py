"""ClaudeAnalyzer drop-in 인터페이스 테스트.

extract_specs와 fetch_first_attachment_text를 monkeypatch해서
AnalyzeResult 합성이 올바른지 + 예외 시 안전한 폴백을 확인.
"""

from __future__ import annotations

from api.llm.extractor import ExtractSpecsResult
from api.llm.schemas import ElecSpec
from api.services import claude_analyzer


def _result(spec: ElecSpec) -> ExtractSpecsResult:
    return ExtractSpecsResult(spec=spec, schema_valid=True, schema_errors=[])


def test_analyze_returns_abb_장비_for_transformer(monkeypatch):
    monkeypatch.setattr(
        claude_analyzer,
        "extract_specs_with_validation",
        lambda **_: _result(ElecSpec(
            product_category="변압기",
            rated_voltage_kv=22.9,
            rated_power_kva=1000.0,
            quantity=2,
        )),
    )
    monkeypatch.setattr(
        claude_analyzer, "fetch_first_attachment_text", lambda *_a, **_kw: None
    )

    analyzer = claude_analyzer.ClaudeAnalyzer()
    result = analyzer.analyze_notice(
        notice_no="T1-00", title="몰드변압기 구매 22.9kV", raw={}
    )

    assert result.category == "ABB장비"
    assert 60 <= result.fit_score <= 90
    assert result.analysis["source"] == "claude_schema_v1"
    assert result.analysis["schema_valid"] is True
    assert result.analysis["elec_spec"]["product_category"] == "변압기"
    assert result.analysis["attachment_used"] is False


def test_analyze_unrelated_returns_비관련_with_zero_score(monkeypatch):
    monkeypatch.setattr(claude_analyzer, "extract_specs_with_validation", lambda **_: _result(ElecSpec()))
    monkeypatch.setattr(
        claude_analyzer, "fetch_first_attachment_text", lambda *_a, **_kw: None
    )

    analyzer = claude_analyzer.ClaudeAnalyzer()
    result = analyzer.analyze_notice(notice_no="X-00", title="도로 포장 공사", raw={})

    assert result.category == "비관련"
    assert result.fit_score == 0


def test_analyze_hil_via_keyword(monkeypatch):
    """ElecSpec에 product_category가 없어도 title 키워드로 HIL 잡힘."""
    monkeypatch.setattr(claude_analyzer, "extract_specs_with_validation", lambda **_: _result(ElecSpec()))
    monkeypatch.setattr(
        claude_analyzer, "fetch_first_attachment_text", lambda *_a, **_kw: None
    )

    analyzer = claude_analyzer.ClaudeAnalyzer()
    result = analyzer.analyze_notice(
        notice_no="H-00", title="Typhoon HIL 시뮬레이터 구매", raw=None
    )

    assert result.category == "HIL"
    assert result.fit_score == 75


def test_analyze_never_raises_on_extractor_exception(monkeypatch):
    def boom(**_):
        raise RuntimeError("anthropic down")

    monkeypatch.setattr(claude_analyzer, "extract_specs_with_validation", boom)
    monkeypatch.setattr(
        claude_analyzer, "fetch_first_attachment_text", lambda *_a, **_kw: None
    )

    analyzer = claude_analyzer.ClaudeAnalyzer()
    result = analyzer.analyze_notice(notice_no="ERR-00", title="x", raw={})

    assert result.category == "비관련"
    assert result.fit_score == 0
    assert "error" in result.analysis


def test_attachment_fetched_when_setting_enabled(monkeypatch):
    """LLM_ATTACHMENT_FETCH=true 일 때 fetch_first_attachment_text가 호출되고
    그 결과 텍스트가 extract_specs로 전달되는지 확인."""
    monkeypatch.setattr(claude_analyzer.settings, "llm_attachment_fetch", True)

    captured: dict = {}

    def capturing_extract(**kwargs):
        captured.update(kwargs)
        return _result(ElecSpec(product_category="변압기"))

    monkeypatch.setattr(claude_analyzer, "extract_specs_with_validation", capturing_extract)
    monkeypatch.setattr(
        claude_analyzer,
        "fetch_first_attachment_text",
        lambda *_a, **_kw: "본문 텍스트 from HWP",
    )

    analyzer = claude_analyzer.ClaudeAnalyzer()
    result = analyzer.analyze_notice(
        notice_no="A-00", title="변압기", raw={"bidNtceNm": "변압기"}
    )

    assert captured["attachment_text"] == "본문 텍스트 from HWP"
    assert result.analysis["attachment_used"] is True


def test_attachment_skipped_when_setting_disabled(monkeypatch):
    monkeypatch.setattr(claude_analyzer.settings, "llm_attachment_fetch", False)

    def never_called(*_a, **_kw):
        raise AssertionError("fetch_first_attachment_text should not be called")

    monkeypatch.setattr(
        claude_analyzer, "fetch_first_attachment_text", never_called
    )
    monkeypatch.setattr(
        claude_analyzer,
        "extract_specs_with_validation",
        lambda **_: _result(ElecSpec(product_category="변압기")),
    )

    analyzer = claude_analyzer.ClaudeAnalyzer()
    result = analyzer.analyze_notice(notice_no="A-01", title="t", raw={"x": 1})
    assert result.analysis["attachment_used"] is False


def test_summary_keys_from_raw_passed_to_extractor(monkeypatch):
    captured: dict = {}

    def capturing_extract(**kwargs):
        captured.update(kwargs)
        return _result(ElecSpec())

    monkeypatch.setattr(claude_analyzer, "extract_specs_with_validation", capturing_extract)
    monkeypatch.setattr(
        claude_analyzer, "fetch_first_attachment_text", lambda *_a, **_kw: None
    )

    raw = {
        "bidNtceNm": "변압기 구매",
        "presmptPrce": "50000000",
        "ntceInsttNm": "조달청",
        "unused_key": "ignored",
    }
    analyzer = claude_analyzer.ClaudeAnalyzer()
    analyzer.analyze_notice(notice_no="S-00", title="변압기", raw=raw)

    summary = captured["raw_json_summary"]
    assert "bidNtceNm: 변압기 구매" in summary
    assert "presmptPrce: 50000000" in summary
    assert "ntceInsttNm: 조달청" in summary
    assert "unused_key" not in summary


def test_analyze_records_schema_validation_errors(monkeypatch):
    monkeypatch.setattr(
        claude_analyzer,
        "extract_specs_with_validation",
        lambda **_: ExtractSpecsResult(
            spec=ElecSpec(),
            schema_valid=False,
            schema_errors=["Input should be a valid number"],
        ),
    )
    monkeypatch.setattr(claude_analyzer, "fetch_first_attachment_text", lambda *_a, **_kw: None)

    analyzer = claude_analyzer.ClaudeAnalyzer()
    result = analyzer.analyze_notice(notice_no="BAD-SCHEMA", title="변압기", raw={})

    assert result.analysis["schema_valid"] is False
    assert result.analysis["schema_errors"] == ["Input should be a valid number"]
