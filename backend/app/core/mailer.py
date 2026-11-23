"""Надсилання email через SMTP (табл. 13 проєкту: «SMTP; на демо - Mailpit»).

Якщо SMTP_HOST у .env порожній, листи не надсилаються, а лише записуються в лог:
так бекенд працює на будь-якому комп'ютері без поштового сервера.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("roadmap.mailer")


def _send_sync(message: EmailMessage) -> None:
    s = get_settings()
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
        if s.smtp_user:
            smtp.starttls()
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(message)


async def send_email(to: str, subject: str, body: str) -> bool:
    """Надсилає лист. Повертає True, якщо лист пішов на SMTP-сервер."""
    s = get_settings()
    if not s.smtp_host:
        log.info("SMTP не налаштовано, лист для %s не надіслано: %s", to, subject)
        return False
    message = EmailMessage()
    message["From"] = s.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    # smtplib блокуючий, тому виконуємо його в окремому потоці, щоб не гальмувати API.
    await asyncio.to_thread(_send_sync, message)
    return True
