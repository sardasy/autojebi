"""api/services/notifications.py — TeamsNotifier 단위 테스트.

httpx.Client는 MockTransport로 격리. dry_run / webhook 빈값 / 200 / 4xx 재시도 케이스.
"""

from __future__ import annotations

import httpx

from api.services.notifications import NotifyOutcome, TeamsNotifier


def test_dry_run_returns_undelivered_with_detail():
    notifier = TeamsNotifier(webhook_url="https://example.test/hook")
    outcome = notifier.deliver(title="t", body="b", dry_run=True)
    assert isinstance(outcome, NotifyOutcome)
    assert outcome.delivered is False
    assert outcome.detail == "dry_run"


def test_missing_webhook_returns_undelivered():
    notifier = TeamsNotifier(webhook_url="")
    outcome = notifier.deliver(title="t", body="b", dry_run=False)
    assert outcome.delivered is False
    assert outcome.detail == "missing_webhook"


def test_can_deliver_reflects_webhook_presence():
    assert TeamsNotifier(webhook_url="https://example.test/hook").can_deliver() is True
    assert TeamsNotifier(webhook_url="").can_deliver() is False
    assert TeamsNotifier(webhook_url="   ").can_deliver() is False


def test_successful_post_returns_delivered(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = request.read().decode("utf-8")
        return httpx.Response(200, text="1")

    mock_client_cls = _make_mock_client_factory(handler)
    monkeypatch.setattr("api.services.notifications.httpx.Client", mock_client_cls)

    notifier = TeamsNotifier(webhook_url="https://example.test/hook")
    outcome = notifier.deliver(title="강원 변압기", body="fit=82", dry_run=False)

    assert outcome.delivered is True
    assert outcome.detail is None
    assert captured["url"] == "https://example.test/hook"
    assert "강원 변압기" in captured["json"]
    assert "fit=82" in captured["json"]


def test_4xx_response_retries_then_fails(monkeypatch):
    counter = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["calls"] += 1
        return httpx.Response(429, text="rate limited")

    mock_client_cls = _make_mock_client_factory(handler)
    monkeypatch.setattr("api.services.notifications.httpx.Client", mock_client_cls)

    notifier = TeamsNotifier(webhook_url="https://example.test/hook")
    outcome = notifier.deliver(title="t", body="b", dry_run=False)

    assert outcome.delivered is False
    assert counter["calls"] == 2
    assert "429" in (outcome.detail or "")


def test_transport_exception_retries_then_fails(monkeypatch):
    counter = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["calls"] += 1
        raise httpx.ConnectError("boom")

    mock_client_cls = _make_mock_client_factory(handler)
    monkeypatch.setattr("api.services.notifications.httpx.Client", mock_client_cls)

    notifier = TeamsNotifier(webhook_url="https://example.test/hook")
    outcome = notifier.deliver(title="t", body="b", dry_run=False)

    assert outcome.delivered is False
    assert counter["calls"] == 2
    assert outcome.detail is not None


_REAL_CLIENT = httpx.Client  # captured before patching


def _make_mock_client_factory(handler):
    """Return a callable that constructs an httpx.Client backed by MockTransport(handler).

    Uses the real httpx.Client captured at import time so that monkeypatching
    ``api.services.notifications.httpx.Client`` does not cause recursion.
    """

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return _REAL_CLIENT(transport=httpx.MockTransport(handler))

    return factory
