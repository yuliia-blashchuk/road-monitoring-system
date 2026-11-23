"""Запити до БД для читання заявок: карта, «Мої звернення», картка, черга служби."""

from collections.abc import Iterable
from dataclasses import dataclass

from geoalchemy2 import Geometry
from sqlalchemy import Select, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.enums import Priority, RequestStatus
from app.modules.admin.models import ProblemType, Service
from app.modules.reports.models import Photo, Request

CopyService = aliased(Service)

# Координати з колонки location (geography) -> два числа для фронтенду.
LAT = func.ST_Y(cast(Request.location, Geometry)).label("lat")
LNG = func.ST_X(cast(Request.location, Geometry)).label("lng")

# Черга: спершу critical, потім high, medium, low (UC-02).
PRIORITY_ORDER = case(
    {
        Priority.CRITICAL: 0,
        Priority.HIGH: 1,
        Priority.MEDIUM: 2,
        Priority.LOW: 3,
    },
    value=Request.priority,
)


@dataclass(frozen=True)
class ReportRow:
    """Заявка разом із даними з довідників (тип, служби) і координатами."""

    request: Request
    problem_code: str
    problem_name: str
    icon: str
    color: str
    service_name: str | None
    copy_service_name: str | None
    lat: float
    lng: float


@dataclass(frozen=True)
class BBox:
    """Видима частина карти: мін./макс. довгота й широта."""

    min_lng: float
    min_lat: float
    max_lng: float
    max_lat: float


def _select() -> Select:
    return (
        select(
            Request,
            ProblemType.code,
            ProblemType.name,
            ProblemType.icon,
            ProblemType.color,
            Service.name,
            CopyService.name,
            LAT,
            LNG,
        )
        .join(ProblemType, ProblemType.id == Request.problem_type_id)
        .outerjoin(Service, Service.id == Request.service_id)
        .outerjoin(CopyService, CopyService.id == Request.copy_service_id)
    )


def _rows(result) -> list[ReportRow]:
    return [ReportRow(*row) for row in result]


async def _count(session: AsyncSession, query: Select) -> int:
    return await session.scalar(select(func.count()).select_from(query.subquery())) or 0


async def map_reports(
    session: AsyncSession,
    statuses: Iterable[RequestStatus],
    types: Iterable[str] | None,
    bbox: BBox | None,
    limit: int,
) -> list[ReportRow]:
    """Заявки для публічної карти. Підозрілі (is_suspicious) на карту не потрапляють."""
    query = _select().where(Request.status.in_(list(statuses)), Request.is_suspicious.is_(False))
    if types:
        query = query.where(ProblemType.code.in_(list(types)))
    if bbox:
        envelope = func.ST_MakeEnvelope(
            bbox.min_lng, bbox.min_lat, bbox.max_lng, bbox.max_lat, 4326
        )
        query = query.where(func.ST_Intersects(cast(Request.location, Geometry), envelope))
    result = await session.execute(
        query.order_by(Request.created_at.desc(), Request.id.desc()).limit(limit)
    )
    return _rows(result)


async def my_reports(
    session: AsyncSession, author_id: int, limit: int, offset: int
) -> tuple[list[ReportRow], int]:
    query = _select().where(Request.author_id == author_id)
    total = await _count(session, query)
    result = await session.execute(
        query.order_by(Request.created_at.desc(), Request.id.desc()).limit(limit).offset(offset)
    )
    return _rows(result), total


async def get_row(session: AsyncSession, request_id: int) -> ReportRow | None:
    rows = _rows(await session.execute(_select().where(Request.id == request_id)))
    return rows[0] if rows else None


async def queue(
    session: AsyncSession,
    statuses: Iterable[RequestStatus],
    *,
    service_id: int | None = None,
    contractor_id: int | None = None,
    everything: bool = False,
    limit: int,
    offset: int,
) -> tuple[list[ReportRow], int]:
    """Черга: заявки служби (основної чи копії), підрядника або всі (адміністратор)."""
    query = _select().where(Request.status.in_(list(statuses)))
    if not everything:
        if service_id is not None:
            query = query.where(
                or_(Request.service_id == service_id, Request.copy_service_id == service_id)
            )
        elif contractor_id is not None:
            query = query.where(Request.contractor_id == contractor_id)
        else:
            query = query.where(Request.id.is_(None))  # немає ні служби, ні підрядника
    total = await _count(session, query)
    result = await session.execute(
        query.order_by(PRIORITY_ORDER, Request.created_at, Request.id).limit(limit).offset(offset)
    )
    return _rows(result), total


async def photo_counts(session: AsyncSession, request_ids: list[int]) -> dict[int, int]:
    if not request_ids:
        return {}
    rows = await session.execute(
        select(Photo.request_id, func.count())
        .where(Photo.request_id.in_(request_ids))
        .group_by(Photo.request_id)
    )
    return {request_id: count for request_id, count in rows}


async def photos(session: AsyncSession, request_id: int) -> list[Photo]:
    rows = await session.scalars(
        select(Photo).where(Photo.request_id == request_id).order_by(Photo.created_at, Photo.id)
    )
    return list(rows)


async def get_photo(session: AsyncSession, request_id: int, photo_id: int) -> Photo | None:
    return await session.scalar(
        select(Photo).where(Photo.id == photo_id, Photo.request_id == request_id)
    )
