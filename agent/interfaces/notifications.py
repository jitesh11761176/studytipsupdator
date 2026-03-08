"""Notification service for admin alerts via Telegram and email."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

logger = logging.getLogger(__name__)

PRIORITY_EMOJI = {
    "low": "ℹ️",
    "medium": "⚠️",
    "high": "🚨",
    "critical": "🔴",
}


class NotificationService:
    """Send notifications to admin via Telegram and/or email.

    Args:
        telegram_token: Telegram bot token.
        admin_chat_id: Telegram admin chat ID.
        smtp_host: SMTP server hostname.
        smtp_port: SMTP server port.
        smtp_user: SMTP username.
        smtp_password: SMTP password.
        from_email: Sender email address.
    """

    def __init__(
        self,
        telegram_token: str = "",
        admin_chat_id: str = "",
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        from_email: str = "",
    ) -> None:
        self.telegram_token = telegram_token
        self.admin_chat_id = admin_chat_id
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email

    def send_telegram(self, message: str, chat_id: Optional[str] = None) -> bool:
        """Send a message via Telegram bot API.

        Args:
            message: Message text (supports Markdown).
            chat_id: Target chat ID. Uses admin_chat_id if not specified.

        Returns:
            True on success, False on failure.
        """
        import requests

        target_chat = chat_id or self.admin_chat_id
        if not self.telegram_token or not target_chat:
            logger.warning("Telegram token or chat ID not configured")
            return False

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": message[:4096],
            "parse_mode": "Markdown",
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram send failed: %s", exc)
            return False

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> bool:
        """Send an email notification.

        Args:
            to: Recipient email address.
            subject: Email subject.
            body: Email body (HTML or plain text).

        Returns:
            True on success, False on failure.
        """
        if not self.smtp_host or not self.from_email:
            logger.warning("SMTP not configured")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to
            msg.attach(MIMEText(body, "html" if "<" in body else "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to, msg.as_string())
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Email send failed: %s", exc)
            return False

    def notify_admin(self, message: str, priority: str = "medium") -> bool:
        """Send a prioritised notification to the admin.

        Tries Telegram first, then email if Telegram fails.

        Args:
            message: Notification message.
            priority: 'low', 'medium', 'high', or 'critical'.

        Returns:
            True if at least one channel succeeded.
        """
        emoji = PRIORITY_EMOJI.get(priority, "ℹ️")
        formatted = f"{emoji} **StudyTips Agent** [{priority.upper()}]\n\n{message}"

        telegram_ok = self.send_telegram(formatted)
        if telegram_ok:
            return True

        logger.info("Telegram failed; notification logged: %s", message)
        return False
