"""Slack incoming webhook 발송기 (sync).

abb-bid-pipeline의 app/notify/slack.py를 sync httpx로 재작성.
Block Kit 포맷은 보존: 헤더 + 사유 + 사양/자격/예가/추천SKU 4-필드 + 위험노트 + 공고 보기 버튼.
tenacity 3회 재시도. 어떤 단계든 실패해도 raise 안함 — NotifyOutcome(delivered=False)로 회수.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from api.config import settings
from api.grading.schemas import ScoreBreakdown

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotifyOutcome:
    delivered: bool
    detail: str | None = None


class SlackNotifier:
    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook = webhook_url or settings.slack_webhook_url

    def send_grade_alert(
        self,
        *,
        title: str,
        breakdown: ScoreBreakdown,
        reason: str | None = None,
        top_sku_name: str | None = None,
        risk_note: str | None = None,
        detail_url: str | None = None,
    ) -> NotifyOutcome:
        if not self._webhook:
            return NotifyOutcome(delivered=False, detail="SLACK_WEBHOOK_URL 비어있음")

        payload = _build_block_kit(
            title=title,
            breakdown=breakdown,
            reason=reason,
            top_sku_name=top_sku_name,
            risk_note=risk_note,
            detail_url=detail_url,
        )
        try:
            _post_with_retry(self._webhook, payload)
            return NotifyOutcome(delivered=True)
        except RetryError as exc:
            log.warning("[slack] 재시도 한도 초과: %s", exc)
            return NotifyOutcome(delivered=False, detail=f"retry exhausted: {exc}")
        except Exception as exc:  # noqa: BLE001
            log.warning("[slack] 발송 실패: %s", exc)
            return NotifyOutcome(delivered=False, detail=str(exc)[:200])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def _post_with_retry(url: str, payload: dict[str, Any]) -> None:
    with httpx.Client(timeout=10) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()


def _build_block_kit(
    *,
    title: str,
    breakdown: ScoreBreakdown,
    reason: str | None,
    top_sku_name: str | None,
    risk_note: str | None,
    detail_url: str | None,
) -> dict[str, Any]:
    short_title = title[:80] + ("…" if len(title) > 80 else "")
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"[적합공고 {breakdown.total:.2f}] {short_title}",
            },
        },
    ]
    if reason:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*적합 사유:* {reason}"},
            }
        )
    blocks.append(
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*사양*\n{breakdown.spec:.2f}"},
                {"type": "mrkdwn", "text": f"*자격*\n{breakdown.qualification:.2f}"},
                {"type": "mrkdwn", "text": f"*예가*\n{breakdown.price:.2f}"},
                {
                    "type": "mrkdwn",
                    "text": f"*추천 SKU*\n{top_sku_name or '없음'}",
                },
            ],
        }
    )
    if risk_note:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":warning: {risk_note}"},
            }
        )
    if detail_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "공고 보기"},
                        "url": detail_url,
                        "style": "primary",
                    }
                ],
            }
        )
    return {
        "blocks": blocks,
        "text": f"적합공고: {short_title} (점수 {breakdown.total:.2f})",
    }
