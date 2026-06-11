"""api/services/slack_notifier.py 단위 테스트.

httpx.Client는 MockTransport로 격리. webhook 빈값 / 정상 / 4xx 케이스.
"""

from __future__ import annotations

import httpx

from api.grading.schemas import ScoreBreakdown
from api.services.slack_notifier import SlackNotifier, _build_block_kit


def _mk_breakdown(total: float = 0.75) -> ScoreBreakdown:
    return ScoreBreakdown(
        spec=0.8, qualification=0.7, price=0.7,
        weights={"spec": 0.5, "qualification": 0.2, "price": 0.3},
        total=total,
    )


def test_returns_undelivered_when_webhook_missing():
    notifier = SlackNotifier(webhook_url="")
    outcome = notifier.send_grade_alert(title="t", breakdown=_mk_breakdown())
    assert outcome.delivered is False
    assert "비어있음" in (outcome.detail or "")


def test_payload_has_header_with_score_and_title():
    payload = _build_block_kit(
        title="강원본부 변압기 시험기",
        breakdown=_mk_breakdown(0.82),
        reason="ABB 적합",
        top_sku_name="RESIBLOC 1000kVA",
        risk_note=None,
        detail_url=None,
    )
    header = payload["blocks"][0]
    assert header["type"] == "header"
    assert "0.82" in header["text"]["text"]
    assert "변압기" in header["text"]["text"]


def test_payload_includes_4_field_grid_and_reason():
    payload = _build_block_kit(
        title="t",
        breakdown=_mk_breakdown(),
        reason="적합 사유",
        top_sku_name="RESIBLOC",
        risk_note=None,
        detail_url=None,
    )
    # reason 섹션 + 4-필드 섹션
    sections = [b for b in payload["blocks"] if b["type"] == "section"]
    assert any("적합 사유" in (s.get("text") or {}).get("text", "") for s in sections)
    field_block = [s for s in sections if "fields" in s]
    assert len(field_block) == 1
    fields = field_block[0]["fields"]
    assert len(fields) == 4
    assert any("사양" in f["text"] for f in fields)
    assert any("RESIBLOC" in f["text"] for f in fields)


def test_payload_appends_risk_note_when_present():
    payload = _build_block_kit(
        title="t",
        breakdown=_mk_breakdown(),
        reason="r",
        top_sku_name=None,
        risk_note="자격 미충족",
        detail_url=None,
    )
    risk_sections = [
        b for b in payload["blocks"]
        if b["type"] == "section" and ":warning:" in str(b.get("text") or "")
    ]
    assert len(risk_sections) == 1


def test_payload_includes_detail_button_when_url():
    payload = _build_block_kit(
        title="t",
        breakdown=_mk_breakdown(),
        reason="r",
        top_sku_name=None,
        risk_note=None,
        detail_url="https://g2b.example.com/notice/1",
    )
    actions = [b for b in payload["blocks"] if b["type"] == "actions"]
    assert len(actions) == 1
    btn = actions[0]["elements"][0]
    assert btn["url"] == "https://g2b.example.com/notice/1"


def test_send_grade_alert_posts_payload(monkeypatch):
    captured: dict = {}

    def fake_post(url: str, payload):
        captured["url"] = url
        captured["payload"] = payload

    monkeypatch.setattr(
        "api.services.slack_notifier._post_with_retry",
        fake_post,
    )

    notifier = SlackNotifier(webhook_url="https://hooks.slack.test/services/T/B/X")
    outcome = notifier.send_grade_alert(
        title="t", breakdown=_mk_breakdown(0.7), reason="r"
    )
    assert outcome.delivered is True
    assert captured["url"].startswith("https://hooks.slack.test")
    assert "blocks" in captured["payload"]


def test_send_grade_alert_returns_undelivered_on_exception(monkeypatch):
    def fake_post(url, payload):
        raise httpx.HTTPError("transport down")

    monkeypatch.setattr(
        "api.services.slack_notifier._post_with_retry",
        fake_post,
    )

    notifier = SlackNotifier(webhook_url="https://hooks.slack.test/X")
    outcome = notifier.send_grade_alert(title="t", breakdown=_mk_breakdown())
    assert outcome.delivered is False
    assert outcome.detail is not None
