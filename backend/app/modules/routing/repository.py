"""Запити до БД модуля routing: правила маршрутизації і зони служб."""

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ServiceKind
from app.modules.admin.models import Service
from app.modules.routing.models import RoutingRule


def _point(latitude: float, longitude: float):
    return func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)


def _covers(latitude: float, longitude: float):
    """Служба без зони обслуговує все місто, інакше точка має лежати в її зоні."""
    return or_(Service.zone.is_(None), func.ST_Contains(Service.zone, _point(latitude, longitude)))


async def matching_rules(
    session: AsyncSession, problem_type_id: int, latitude: float, longitude: float
) -> list[tuple[RoutingRule, Service]]:
    """Активні правила для типу, служба яких обслуговує точку (RoutingRule.matches()).

    Першою йде служба з найменшою зоною - найточніший збіг (район важливіший за місто).
    """
    rows = await session.execute(
        select(RoutingRule, Service)
        .join(Service, Service.id == RoutingRule.service_id)
        .where(
            RoutingRule.problem_type_id == problem_type_id,
            RoutingRule.is_active,
            Service.is_active,
            _covers(latitude, longitude),
        )
        .order_by(Service.zone.is_(None), func.ST_Area(Service.zone), RoutingRule.id)
    )
    return [(rule, service) for rule, service in rows]


async def get_service(session: AsyncSession, service_id: int) -> Service | None:
    return await session.get(Service, service_id)


async def service_in_zone(
    session: AsyncSession,
    kind: ServiceKind,
    latitude: float,
    longitude: float,
    prefer_id: int | None = None,
) -> Service | None:
    """Активна служба потрібного виду, яка обслуговує точку. prefer_id - якщо підходить."""
    return await session.scalar(
        select(Service)
        .where(Service.kind == kind, Service.is_active, _covers(latitude, longitude))
        .order_by(
            case((Service.id == prefer_id, 0), else_=1),
            Service.zone.is_(None),
            func.ST_Area(Service.zone),
        )
        .limit(1)
    )
