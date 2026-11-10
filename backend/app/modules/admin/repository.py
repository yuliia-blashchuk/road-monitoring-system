"""Запити до БД довідників і політик доступу."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.admin.models import AccessPolicy, ProblemType, Service
from app.modules.routing.models import RoutingRule


async def active_problem_types(session: AsyncSession) -> list[ProblemType]:
    rows = await session.scalars(
        select(ProblemType).where(ProblemType.is_active).order_by(ProblemType.id)
    )
    return list(rows)


async def problem_type_by_code(session: AsyncSession, code: str) -> ProblemType | None:
    return await session.scalar(select(ProblemType).where(ProblemType.code == code))


async def add_problem_type(session: AsyncSession, item: ProblemType) -> ProblemType:
    session.add(item)
    await session.flush()
    return item


async def routing_rules(session: AsyncSession) -> list:
    copy_service = aliased(Service)
    rows = await session.execute(
        select(
            RoutingRule.id,
            ProblemType.code.label("problem_type"),
            Service.name.label("service"),
            copy_service.name.label("copy_service"),
            RoutingRule.initial_priority,
            RoutingRule.is_active,
        )
        .join(ProblemType, ProblemType.id == RoutingRule.problem_type_id)
        .join(Service, Service.id == RoutingRule.service_id)
        .outerjoin(copy_service, copy_service.id == RoutingRule.copy_service_id)
        .order_by(RoutingRule.id)
    )
    return list(rows.mappings())


async def access_policies(session: AsyncSession) -> list[AccessPolicy]:
    rows = await session.scalars(
        select(AccessPolicy).order_by(AccessPolicy.resource, AccessPolicy.action, AccessPolicy.role)
    )
    return list(rows)
