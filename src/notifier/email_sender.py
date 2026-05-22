import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.config import settings
from src.db.models import Bid
from src.notifier.templates.email_template import build_email_body

logger = logging.getLogger(__name__)


async def send_email_notification(bids: list[Bid]) -> bool:
    if not settings.smtp_host or not settings.recipient_list:
        logger.warning("SMTP 설정 미완료")
        return False

    body = build_email_body(bids, datetime.now())
    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"[입찰알림] 오늘의 맞춤 공고 {len(bids)}건 — {date_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = ", ".join(settings.recipient_list)
    msg.attach(MIMEText(body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            if settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_user, settings.recipient_list, msg.as_string())
        logger.info(f"이메일 발송: {settings.recipient_list}")
        return True
    except Exception as e:
        logger.error(f"이메일 발송 실패: {e}")
        return False
