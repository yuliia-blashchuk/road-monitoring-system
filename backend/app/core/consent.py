"""Перевірка згоди водія на сервері (KAN-65, п. 3.5, табл. 15).

Чинна згода - запис Consent без revoked_at з актуальною версією тексту
(settings.consent_version). Перед кожною дією з персональними даними водія:

| Дія                                         | Потрібна згода       |
| ------------------------------------------- | -------------------- |
| створити заявку                              | terms, personal_data |
| передати службі фото й коментар              | media_sharing        |
| розкрити диспетчеру контакт автора           | contact              |
| надіслати лист про зміну статусу             | email_notifications  |

Без згоди дія не виконується (403 + ACCESS_DENIED в AuditLog з причиною
consent_missing:<тип>) або службі передаються лише публічні поля (filter_media).
Дані працівників служб і підрядників обробляються на іншій підставі (п. 3.5),
тому для них перевірка не виконується.

Створення заявки вже перевіряє personal_data і media_sharing (reports/service.py,
KAN-57). Цей модуль - для решти дій, де потрібна згода:

    # розкриття контакту автора диспетчеру
    @router.post("/{report_id}/contact")
    async def reveal_contact(user: Annotated[User, Depends(require_consent(CONTACT))], ...)

    # черга служби / картка для підрядника: без media_sharing - лише публічні поля
    views = await filter_media_for_service(session, views, [r.author_id for r in rows])
"""

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import access_role, deny
from app.core.config import get_settings
from app.core.enums import ConsentType, RoleCode
from app.modules.users.dependencies import CurrentUser, SessionDep
from app.modules.users.models import Consent, User

MEDIA = ConsentType.MEDIA_SHARING
CONTACT = ConsentType.CONTACT
REPORT_CONSENTS = (ConsentType.TERMS, ConsentType.PERSONAL_DATA)
# Поля заявки, які без media_sharing не передаються службам (табл. 15).
MEDIA_FIELDS = ("comment", "photos")

MESSAGES: dict[ConsentType, str] = {
    ConsentType.TERMS: "прийняти правила користування",
    ConsentType.PERSONAL_DATA: "дати згоду на обробку персональних даних",
    ConsentType.MEDIA_SHARING: "дозволити передачу фото й коментаря службам",
    ConsentType.CONTACT: "дозволити диспетчеру зв'язатися з вами",
    ConsentType.EMAIL_NOTIFICATIONS: "увімкнути сповіщення email",
}


def needs_consent(user: User) -> bool:
    """Згода стосується лише водіїв (п. 3.5)."""
    return user.role.code == RoleCode.DRIVER


async def active_consent_types(
    session: AsyncSession, user_ids: Iterable[int], consent_type: ConsentType
) -> set[int]:
    """Хто з користувачів має чинну згоду цього типу (одним запитом для черги заявок)."""
    ids = {i for i in user_ids if i is not None}
    if not ids:
        return set()
    rows = await session.scalars(
        select(Consent.user_id).where(
            Consent.user_id.in_(ids),
            Consent.type == consent_type,
            Consent.revoked_at.is_(None),
            Consent.version == get_settings().consent_version,
        )
    )
    return set(rows)


async def has_consent(session: AsyncSession, user_id: int, consent_type: ConsentType) -> bool:
    return user_id in await active_consent_types(session, [user_id], consent_type)


async def missing_consents(
    session: AsyncSession, user: User, types: Iterable[ConsentType]
) -> list[ConsentType]:
    if not needs_consent(user):
        return []
    return [t for t in types if not await has_consent(session, user.id, t)]


async def consent_denied(user: User, missing: list[ConsentType], *, endpoint: str) -> HTTPException:
    """403 з переліком згод, яких бракує, і запис ACCESS_DENIED в AuditLog."""
    exc = await deny(
        user,
        access_role(user),
        "consent",
        "check",
        endpoint,
        reason="consent_missing:" + ",".join(t.value for t in missing),
    )
    actions = "; ".join(MESSAGES[t] for t in missing)
    exc.detail = {
        "message": f"Для цієї дії потрібно {actions}",
        "missing_consents": [t.value for t in missing],
    }
    return exc


def require_consent(*types: ConsentType) -> Callable[..., Awaitable[User]]:
    """Залежність FastAPI: пропускає водія лише з чинними згодами потрібних типів."""

    async def dependency(request: Request, user: CurrentUser, session: SessionDep) -> User:
        missing = await missing_consents(session, user, types)
        if missing:
            raise await consent_denied(
                user, missing, endpoint=f"{request.method} {request.url.path}"
            )
        return user

    dependency.__name__ = "require_consent_" + "_".join(t.value for t in types)
    return dependency


def filter_media(report: dict[str, Any], media_allowed: bool) -> dict[str, Any]:
    """Без згоди media_sharing служба отримує заявку без фото й коментаря (табл. 15).

    Застосовується після filter_request() (класифікація) для диспетчера й поліції.
    """
    if media_allowed:
        return report
    return {k: v for k, v in report.items() if k not in MEDIA_FIELDS}


async def filter_media_for_service(
    session: AsyncSession, reports: list[dict[str, Any]], author_ids: list[int | None]
) -> list[dict[str, Any]]:
    """filter_media для списку заявок (черга служби): одна перевірка згод на всіх авторів.

    author_ids[i] - автор reports[i]. Якщо автора вже немає (анонімізовано), медіа
    не передається: згоду перевірити неможливо.
    """
    allowed = await active_consent_types(session, author_ids, MEDIA)
    return [
        filter_media(report, author_id in allowed)
        for report, author_id in zip(reports, author_ids, strict=True)
    ]
