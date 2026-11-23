"""Сповіщення автору заявки про зміну статусу (KAN-61, UC-03, F-18, QR-03).

Модуль підписаний на подію StatusChanged із внутрішньої шини (app/core/events.py):
модуль заявок нічого не знає про сповіщення, він лише публікує подію.
Сповіщення зберігаються в таблиці notification і показуються у стрічці водія;
email отримують лише ті, хто дав згоду email_notifications (п. 3.5).
"""

import logging

from app.core import events, mailer
from app.core.database import SessionLocal
from app.core.enums import ConsentType, RequestStatus
from app.modules.notifications import repository as repo
from app.modules.reports.lifecycle import STATUS_LABELS
from app.modules.users import service as users_service

log = logging.getLogger("roadmap.notifications")

STATUS_CHANGED = "STATUS_CHANGED"


def build_message(event: events.StatusChanged, service_name: str | None) -> str:
    """Текст сповіщення: статус, служба, коментар, строк (UC-03, крок 2)."""
    parts = [f"Заявка №{event.number}: статус змінено на «{STATUS_LABELS[event.to_status]}»."]
    if service_name:
        parts.append(f"Служба: {service_name}.")
    if event.comment:
        label = "Причина" if event.to_status == RequestStatus.REJECTED else "Коментар"
        parts.append(f"{label}: {event.comment.rstrip('.')}.")
    if event.deadline and event.to_status in (RequestStatus.ACCEPTED, RequestStatus.IN_PROGRESS):
        parts.append(f"Орієнтовний строк: {event.deadline:%d.%m.%Y}.")
    if event.to_status == RequestStatus.RESOLVED:
        parts.append("Оцініть, будь ласка, результат у картці заявки.")
    return " ".join(parts)


async def on_status_changed(event: events.StatusChanged) -> None:
    """Створює сповіщення в окремій транзакції - після того, як статус уже збережено."""
    async with SessionLocal() as session:
        users = await repo.recipients(session, event.request_id, event.author_id, event.changed_by)
        if not users:
            return
        message = build_message(event, await repo.service_name(session, event.service_id))
        await repo.add_many(
            session, [u.id for u in users], event.request_id, STATUS_CHANGED, message
        )
        await session.commit()

        # Email - лише за згодою. Збій пошти не скасовує сповіщення в застосунку.
        for user in users:
            if not await users_service.has_consent(session, user, ConsentType.EMAIL_NOTIFICATIONS):
                continue
            try:
                await mailer.send_email(
                    user.email,
                    f"RoadMap: заявка №{event.number} - {STATUS_LABELS[event.to_status]}",
                    message,
                )
            except Exception:
                log.exception("Не вдалося надіслати лист користувачу %s", user.id)


# Підписка спрацьовує, коли застосунок імпортує модуль сповіщень (через router.py).
events.subscribe(events.StatusChanged, on_status_changed)