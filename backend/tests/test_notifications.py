"""Сповіщення автору про зміну статусу (KAN-61, UC-03, QR-03)."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.enums import RequestStatus
from app.modules.notifications import repository as notifications_repo
from app.modules.notifications.models import Notification
from app.modules.notifications.service import build_message
from app.modules.reports.models import Confirmation, Request
from tests.factories import make_driver, make_staff
from tests.test_reports_status import WEST, new_report, patch


async def notifications_of(db: AsyncSession, user_id: int) -> list[Notification]:
    rows = await db.scalars(
        select(Notification).where(Notification.user_id == user_id).order_by(Notification.id)
    )
    return list(rows)


async def test_author_notified_on_status_change(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    deadline = date.today() + timedelta(days=3)

    response = await patch(
        client,
        dispatcher,
        report["id"],
        status="accepted",
        comment="Бригада виїде",
        deadline=deadline.isoformat(),
    )
    assert response.status_code == 200

    [note] = await notifications_of(db, report["author"].id)
    assert note.request_id == report["id"]
    assert note.type == "STATUS_CHANGED"
    assert note.is_read is False
    assert note.message == (
        f"Заявка №{report['number']}: статус змінено на «Прийнята». "
        f"Служба: {WEST}. Коментар: Бригада виїде. "
        f"Орієнтовний строк: {deadline:%d.%m.%Y}."
    )


async def test_every_change_creates_notification(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    for target in ("accepted", "in_progress", "resolved"):
        await patch(client, dispatcher, report["id"], status=target)

    messages = [n.message for n in await notifications_of(db, report["author"].id)]
    assert len(messages) == 3
    assert "«Усунена»" in messages[-1] and "Оцініть" in messages[-1]


async def test_reject_reason_in_message(client: AsyncClient, db: AsyncSession) -> None:
    """UC-02 A2: автор отримує причину відхилення."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, report["id"], status="rejected", reject_reason="Дубль заявки")

    [note] = await notifications_of(db, report["author"].id)
    assert "«Відхилена»" in note.message and "Причина: Дубль заявки." in note.message


async def test_confirmers_notified_too(client: AsyncClient, db: AsyncSession) -> None:
    """UC-03: сповіщення отримують автор і всі, хто підтвердив заявку («Теж бачу»)."""
    report = await new_report(client, db)
    witness = await make_driver(db, email="witness@test.ua")
    db.add(Confirmation(request_id=report["id"], user_id=witness.id))
    await db.commit()
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)

    await patch(client, dispatcher, report["id"], status="accepted")
    assert len(await notifications_of(db, report["author"].id)) == 1
    assert len(await notifications_of(db, witness.id)) == 1
    assert await notifications_of(db, dispatcher.id) == []  # той, хто змінив, - ні


async def test_failed_rejection_sends_nothing(client: AsyncClient, db: AsyncSession) -> None:
    """Якщо статус не змінився (409, 422), сповіщень немає."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    assert (await patch(client, dispatcher, report["id"], status="resolved")).status_code == 409
    assert (await patch(client, dispatcher, report["id"], status="rejected")).status_code == 422
    assert await notifications_of(db, report["author"].id) == []


async def test_notification_failure_keeps_status(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Збій сповіщень не скасовує зміну статусу (п. 4.7: обробка подій окремо)."""

    async def broken(*args, **kwargs):
        raise RuntimeError("БД сповіщень недоступна")

    monkeypatch.setattr(notifications_repo, "add_many", broken)
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)

    response = await patch(client, dispatcher, report["id"], status="accepted")
    assert response.status_code == 200
    assert (await db.get(Request, report["id"])).status == "accepted"
    assert await notifications_of(db, report["author"].id) == []


def test_message_without_service_and_comment() -> None:
    event = events.StatusChanged(
        request_id=1,
        number=1001,
        author_id=1,
        from_status=RequestStatus.ACCEPTED,
        to_status=RequestStatus.IN_PROGRESS,
        changed_by=2,
        service_id=None,
    )
    assert build_message(event, None) == "Заявка №1001: статус змінено на «В роботі»."


def test_deadline_only_while_work_planned() -> None:
    """Строк показуємо, поки роботи заплановані; у «Виконана»/«Усунена» він уже не потрібен."""
    base = {
        "request_id": 1,
        "number": 7,
        "author_id": 1,
        "changed_by": 2,
        "service_id": None,
        "deadline": date(2026, 12, 1),
    }
    accepted = events.StatusChanged(
        **base, from_status=RequestStatus.NEW, to_status=RequestStatus.ACCEPTED
    )
    resolved = events.StatusChanged(
        **base, from_status=RequestStatus.IN_PROGRESS, to_status=RequestStatus.RESOLVED
    )
    assert "01.12.2026" in build_message(accepted, None)
    assert "строк" not in build_message(resolved, None)
