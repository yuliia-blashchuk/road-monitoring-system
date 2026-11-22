"""Запити до БД модуля reports. Інші модулі сюди напряму не звертаються."""

from datetime import datetime

from geoalchemy2 import WKTElement
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RequestStatus
from app.modules.reports.models import Request, StatusHistory


def point(latitude: float, longitude: float) -> WKTElement:
    """Точка WGS84 (SRID 4326). У WKT спершу довгота, потім широта."""
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


async def add_request(session: AsyncSession, request: Request) -> Request:
    session.add(request)
    await session.flush()
    await session.refresh(request, ["number", "status", "priority", "created_at"])
    return request


async def add_first_status(session: AsyncSession, request: Request, user_id: int) -> None:
    """Перший запис історії: заявку створено зі статусом «Нова»."""
    session.add(
        StatusHistory(
            request_id=request.id,
            from_status=None,
            to_status=RequestStatus.NEW,
            changed_by=user_id,
        )
    )


async def get_request(session: AsyncSession, request_id: int) -> Request | None:
    return await session.get(Request, request_id)


async def list_history(session: AsyncSession, request_id: int) -> list[StatusHistory]:
    """Історія статусів від найстарішого запису до найновішого."""
    rows = await session.scalars(
        select(StatusHistory)
        .where(StatusHistory.request_id == request_id)
        .order_by(StatusHistory.changed_at, StatusHistory.id)
    )
    return list(rows)


async def get_for_update(session: AsyncSession, request_id: int) -> Request | None:
    """Заявка з блокуванням рядка до кінця транзакції: два диспетчери не змінять
    статус одночасно (друга зміна побачить уже новий статус)."""
    return await session.scalar(select(Request).where(Request.id == request_id).with_for_update())


async def add_status(
    session: AsyncSession,
    request: Request,
    from_status: RequestStatus,
    to_status: RequestStatus,
    user_id: int,
    comment: str | None,
) -> StatusHistory:
    entry = StatusHistory(
        request_id=request.id,
        from_status=from_status,
        to_status=to_status,
        changed_by=user_id,
        comment=comment,
    )
    session.add(entry)
    await session.flush()
    await session.refresh(entry, ["changed_at"])
    return entry


async def count_since(session: AsyncSession, author_id: int, since: datetime) -> int:
    """Скільки заявок автор створив починаючи з моменту since (ліміт E3)."""
    return await session.scalar(
        select(func.count())
        .select_from(Request)
        .where(Request.author_id == author_id, Request.created_at >= since)
    )
