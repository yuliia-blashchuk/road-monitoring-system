"""Запити до БД модуля dedup: пошук заявок поруч і підтвердження «Теж бачу»."""

from dataclasses import dataclass

from geoalchemy2 import Geography, Geometry
from sqlalchemy import cast, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RequestStatus
from app.modules.reports.models import Confirmation, Request

# Закриті заявки не вважаються дублікатами: проблему вже усунено або відхилено.
CLOSED_STATUSES = (RequestStatus.RESOLVED, RequestStatus.REJECTED)


@dataclass(frozen=True)
class NearbyRow:
    request: Request
    distance_m: float
    lat: float
    lng: float


def point(lat: float, lng: float):
    """Точка WGS 84 як geography: відстані рахуються в метрах."""
    return cast(func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326), Geography(srid=4326))


async def find_nearby(
    session: AsyncSession,
    *,
    lat: float,
    lng: float,
    problem_type_id: int,
    radius_m: float,
    limit: int,
) -> list[NearbyRow]:
    """Активні заявки того самого типу в радіусі radius_m, найближчі першими.

    ST_DWithin на geography використовує геоіндекс GiST на request.location.
    """
    target = point(lat, lng)
    distance = func.ST_Distance(Request.location, target)
    geom = cast(Request.location, Geometry)
    stmt = (
        select(
            Request,
            distance.label("distance_m"),
            func.ST_Y(geom).label("lat"),
            func.ST_X(geom).label("lng"),
        )
        .where(
            Request.problem_type_id == problem_type_id,
            Request.status.not_in(CLOSED_STATUSES),
            func.ST_DWithin(Request.location, target, radius_m),
        )
        .order_by(distance, Request.id)
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return [NearbyRow(r.Request, float(r.distance_m), float(r.lat), float(r.lng)) for r in rows]


async def get_request_for_update(session: AsyncSession, request_id: int) -> Request | None:
    """Заявка з блокуванням рядка: два одночасні «Теж бачу» не загублять лічильник."""
    return await session.scalar(select(Request).where(Request.id == request_id).with_for_update())


async def has_confirmation(session: AsyncSession, request_id: int, user_id: int) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(
                    Confirmation.request_id == request_id, Confirmation.user_id == user_id
                )
            )
        )
    )


def add_confirmation(session: AsyncSession, request_id: int, user_id: int) -> Confirmation:
    item = Confirmation(request_id=request_id, user_id=user_id)
    session.add(item)
    return item
