import asyncio
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)
from src.config import settings
from src.db.models import Bid
from src.notifier.templates.email_template import build_email_body

logger = logging.getLogger(__name__)


_TRANSIENT = (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
              smtplib.SMTPHeloError, smtplib.SMTPDataError, TimeoutError, OSError)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_TRANSIENT),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _send_sync(targets: list[str], message: str) -> None:
    """Blocking SMTP send; runs in thread via asyncio.to_thread."""
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.ehlo()
        server.starttls()
        if settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_user, targets, message)


async def send_email_notification(
    bids: list[Bid],
    recipients: list[str] | None = None,
    rule_name: str | None = None,
) -> bool:
    targets = recipients if recipients is not None else settings.recipient_list
    if not settings.smtp_host or not targets:
        logger.warning("SMTP 설정 미완료 (rule=%s)", rule_name or "-")
        return False

    body = build_email_body(bids, datetime.now())
    date_str = datetime.now().strftime("%Y-%m-%d")
    rule_suffix = f" [{rule_name}]" if rule_name and rule_name != "default" else ""
    subject = f"[입찰알림]{rule_suffix} 오늘의 맞춤 공고 {len(bids)}건 — {date_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = ", ".join(targets)
    msg.attach(MIMEText(body, "html", "utf-8"))

    try:
        await asyncio.to_thread(_send_sync, targets, msg.as_string())
        logger.info("이메일 발송: %s (rule=%s)", targets, rule_name or "-")
        return True
    except Exception:
        logger.exception("이메일 발송 실패 (rule=%s)", rule_name or "-")
        return False
