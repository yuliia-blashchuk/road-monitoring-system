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


async def count_since(session: AsyncSession, author_id: int, since: datetime) -> int:
    """Скільки заявок автор створив починаючи з моменту since (ліміт E3)."""
    return await session.scalar(
        select(func.count())
        .select_from(Request)
        .where(Request.author_id == author_id, Request.created_at >= since)
    )
