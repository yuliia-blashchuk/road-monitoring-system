"""Запити до БД модуля сповіщень."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models import Service
from app.modules.notifications.models import Notification
from app.modules.reports.models import Confirmation
from app.modules.users.models import User


async def recipients(
    session: AsyncSession, request_id: int, author_id: int | None, exclude_id: int | None
) -> list[User]:
    """Кому надсилати сповіщення про заявку: автору й усім, хто її підтвердив
    («Теж бачу», UC-03), крім того, хто сам змінив статус. Лише активні акаунти."""
    ids: set[int] = {author_id} if author_id else set()
    confirmers = await session.scalars(
        select(Confirmation.user_id).where(
            Confirmation.request_id == request_id, Confirmation.user_id.is_not(None)
        )
    )
    ids.update(confirmers)
    ids.discard(exclude_id)
    if not ids:
        return []
    rows = await session.scalars(
        select(User).where(User.id.in_(ids), User.is_active.is_(True)).order_by(User.id)
    )
    return list(rows)


async def service_name(session: AsyncSession, service_id: int | None) -> str | None:
    if service_id is None:
        return None
    return await session.scalar(select(Service.name).where(Service.id == service_id))


async def add_many(
    session: AsyncSession, user_ids: list[int], request_id: int, kind: str, message: str
) -> list[Notification]:
    items = [
        Notification(user_id=user_id, request_id=request_id, type=kind, message=message)
        for user_id in user_ids
    ]
    session.add_all(items)
    await session.flush()
    return items