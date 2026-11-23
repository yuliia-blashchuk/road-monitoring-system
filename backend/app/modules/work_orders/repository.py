"""Запити до БД цього модуля. Інші модулі сюди напряму не звертаються."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AccessScope, PhotoKind, RequestStatus
from app.modules.admin.models import Contractor, ProblemType
from app.modules.reports.models import Photo, Request
from app.modules.users.models import User

_ROW = (Request, Contractor.name.label("contractor_name"), ProblemType.code.label("problem_code"))


def _base():
    return (
        select(*_ROW)
        .join(ProblemType, ProblemType.id == Request.problem_type_id)
        .outerjoin(Contractor, Contractor.id == Request.contractor_id)
        .where(Request.contractor_id.is_not(None))
    )


async def get_contractor(session: AsyncSession, contractor_id: int) -> Contractor | None:
    return await session.get(Contractor, contractor_id)


async def get_row(session: AsyncSession, request_id: int):
    """Заявка з підрядником і кодом типу проблеми (після призначення)."""
    return (await session.execute(_base().where(Request.id == request_id))).one_or_none()


async def list_rows(
    session: AsyncSession,
    scope: AccessScope,
    user: User,
    status: RequestStatus | None,
    limit: int,
    offset: int,
):
    """Об'єкти ремонту в області дії ролі: підрядник - лише свої, служба - своєї служби
    (зокрема копії), адміністратор - усі."""
    query = _base()
    match scope:
        case AccessScope.OWN:
            query = query.where(Request.contractor_id == user.contractor_id)
        case AccessScope.SERVICE:
            query = query.where(
                or_(
                    Request.service_id == user.service_id,
                    Request.copy_service_id == user.service_id,
                )
            )
    if status is not None:
        query = query.where(Request.status == status)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(Request.deadline.asc().nulls_last(), Request.id).limit(limit).offset(offset)
    )
    return rows.all(), total


async def count_photos(session: AsyncSession, request_id: int, kind: PhotoKind) -> int:
    return await session.scalar(
        select(func.count())
        .select_from(Photo)
        .where(Photo.request_id == request_id, Photo.kind == kind)
    )
