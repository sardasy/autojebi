import logging
from datetime import datetime
import httpx
from src.config import settings
from src.db.models import Bid
from src.notifier.templates.teams_message import build_teams_payload

logger = logging.getLogger(__name__)


async def send_teams_notification(
    bids: list[Bid],
    webhook: str | None = None,
    rule_name: str | None = None,
) -> bool:
    url = webhook or settings.teams_webhook_url
    if not url:
        logger.warning("Teams webhook URL 미설정 (rule=%s)", rule_name or "-")
        return False

    payload = build_teams_payload(bids, datetime.now())
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        logger.info("Teams 알림 발송: %s건 (rule=%s)", len(bids), rule_name or "-")
        return True
    except Exception as e:
        logger.error("Teams 알림 실패: %s", e)
        return False
