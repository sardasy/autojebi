import logging
from datetime import datetime
import httpx
from src.config import settings
from src.db.models import Bid
from src.notifier.templates.teams_message import build_teams_payload

logger = logging.getLogger(__name__)


async def send_teams_notification(bids: list[Bid]) -> bool:
    if not settings.teams_webhook_url:
        logger.warning("Teams webhook URL 미설정")
        return False

    payload = build_teams_payload(bids, datetime.now())
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(settings.teams_webhook_url, json=payload)
            response.raise_for_status()
        logger.info(f"Teams 알림 발송: {len(bids)}건")
        return True
    except Exception as e:
        logger.error(f"Teams 알림 실패: {e}")
        return False
