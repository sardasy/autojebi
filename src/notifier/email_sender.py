import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.config import settings
from src.db.models import Bid
from src.notifier.templates.email_template import build_email_body

logger = logging.getLogger(__name__)


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
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            if settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_user, targets, msg.as_string())
        logger.info("이메일 발송: %s (rule=%s)", targets, rule_name or "-")
        return True
    except Exception as e:
        logger.error("이메일 발송 실패: %s", e)
        return False
