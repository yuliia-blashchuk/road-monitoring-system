"""Запити до БД модуля сповіщень."""

from sqlalchemy import func, select, update
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


async def list_for_user(
    session: AsyncSession, user_id: int, unread_only: bool, limit: int, offset: int
) -> tuple[list[Notification], int]:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0


async def count_unread(session: AsyncSession, user_id: int) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        or 0
    )


async def get_own(session: AsyncSession, notification_id: int, user_id: int) -> Notification | None:
    """Сповіщення лише цього користувача: чуже повертає None (як «не знайдено»)."""
    return await session.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
    )


async def mark_all_read(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    return result.rowcount or 0
