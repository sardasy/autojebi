from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class NotifyOutcome:
    delivered: bool
    detail: str | None = None


class TeamsNotifier:
    def __init__(self, *, webhook_url: str | None = None) -> None:
        self._webhook_url = (webhook_url or os.getenv("TEAMS_WEBHOOK_URL") or "").strip()

    def can_deliver(self) -> bool:
        return bool(self._webhook_url)

    def deliver(self, *, title: str, body: str, dry_run: bool = True) -> NotifyOutcome:
        if dry_run:
            return NotifyOutcome(delivered=False, detail="dry_run")
        if not self._webhook_url:
            return NotifyOutcome(delivered=False, detail="missing_webhook")

        payload = {
            "text": f"{title}\n\n{body}",
        }

        timeout = httpx.Timeout(5.0, connect=5.0)
        with httpx.Client(timeout=timeout) as client:
            # Minimal retry: 2 attempts total
            last_exc: Exception | None = None
            for _ in range(2):
                try:
                    resp = client.post(self._webhook_url, json=payload)
                    if 200 <= resp.status_code < 300:
                        return NotifyOutcome(delivered=True)
                    last_exc = RuntimeError(f"Teams webhook status={resp.status_code}")
                except Exception as e:
                    last_exc = e
            return NotifyOutcome(delivered=False, detail=str(last_exc) if last_exc else "failed")

