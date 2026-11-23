"""Email-сповіщення про зміну статусу (KAN-61): лише за згодою, збій пошти не заважає."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import mailer
from app.core.config import get_settings
from app.core.enums import ConsentType
from app.modules.notifications.models import Notification
from app.modules.users import repository as users_repo
from tests.factories import make_staff
from tests.test_reports_status import WEST, new_report, patch


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Підміняє надсилання листів: замість SMTP листи складаються в список."""
    letters: list[dict] = []

    async def fake_send(to: str, subject: str, body: str) -> bool:
        letters.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr(mailer, "send_email", fake_send)
    return letters


async def allow_email(db: AsyncSession, user) -> None:
    await users_repo.add_consents(
        db, user, [ConsentType.EMAIL_NOTIFICATIONS], get_settings().consent_version
    )
    await db.commit()


async def test_email_sent_with_consent(
    client: AsyncClient, db: AsyncSession, sent: list[dict]
) -> None:
    report = await new_report(client, db)
    await allow_email(db, report["author"])
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)

    await patch(client, dispatcher, report["id"], status="accepted", comment="Виїдемо завтра")

    [letter] = sent
    assert letter["to"] == report["author"].email
    assert letter["subject"] == f"RoadMap: заявка №{report['number']} - Прийнята"
    assert "Коментар: Виїдемо завтра." in letter["body"]


async def test_no_email_without_consent(
    client: AsyncClient, db: AsyncSession, sent: list[dict]
) -> None:
    """Без згоди email_notifications лист не надсилається, але сповіщення в застосунку є."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, report["id"], status="accepted")

    assert sent == []
    count = await db.scalar(select(func.count()).select_from(Notification))
    assert count == 1


async def test_smtp_failure_keeps_everything(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пошта недоступна: статус змінено, сповіщення в застосунку збережено."""

    async def broken(*args, **kwargs) -> bool:
        raise ConnectionRefusedError("SMTP не відповідає")

    monkeypatch.setattr(mailer, "send_email", broken)
    report = await new_report(client, db)
    await allow_email(db, report["author"])
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)

    response = await patch(client, dispatcher, report["id"], status="accepted")
    assert response.status_code == 200
    count = await db.scalar(select(func.count()).select_from(Notification))
    assert count == 1


async def test_mailer_disabled_without_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без SMTP_HOST лист не надсилається (лише лог) - так працює локальний запуск і CI."""
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    assert await mailer.send_email("a@test.ua", "Тема", "Текст") is False