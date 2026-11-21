"""Бізнес-логіка заявок: створення заявки водієм (UC-01, KAN-57).

Перевірки йдуть у порядку з п. 3.6: спершу схема Pydantic (типи, межі значень,
довжина коментаря), далі правила, яким потрібна БД (тип з довідника, межі міста),
а обмеження таблиць - остання лінія захисту.
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin import repository as reference
from app.modules.reports import repository as repo
from app.modules.reports.models import Request
from app.modules.reports.schemas import ReportCreatedOut, ReportCreateForm
from app.modules.users.models import User

OFFLINE_MAX_AGE = timedelta(hours=24)  # QR-06, DQ-09
CLOCK_SKEW = timedelta(minutes=5)  # годинник телефона може трохи поспішати


def field_error(field: str, message: str, code: int = status.HTTP_422_UNPROCESSABLE_CONTENT):
    """Помилка у форматі FastAPI: фронтенд підсвічує поле з назвою field."""
    return HTTPException(code, detail=[{"loc": ["body", field], "msg": message}])


def _check_device_time(value: datetime | None) -> None:
    if value is None:
        return
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if value > now + CLOCK_SKEW:
        raise field_error("device_created_at", "Час створення заявки не може бути в майбутньому")
    if value < now - OFFLINE_MAX_AGE:
        raise field_error(
            "device_created_at",
            "Заявка створена понад 24 год тому - підтвердіть, що проблема ще існує",
        )


async def create_report(
    session: AsyncSession, user: User, data: ReportCreateForm
) -> ReportCreatedOut:
    problem_type = await reference.problem_type_by_code(session, data.problem_type)
    if problem_type is None or not problem_type.is_active:
        raise field_error("problem_type", "Невідомий тип проблеми")  # DQ-02

    if not await reference.point_in_city(session, data.latitude, data.longitude):
        raise field_error("location", "Ділянка не обслуговується")  # DQ-03, E2

    _check_device_time(data.device_created_at)

    request = await repo.add_request(
        session,
        Request(
            author_id=user.id,
            problem_type_id=problem_type.id,
            location=repo.point(data.latitude, data.longitude),
            address=data.address,
            comment=data.comment,
            device_created_at=data.device_created_at,
        ),
    )
    await repo.add_first_status(session, request, user.id)
    await session.commit()

    return ReportCreatedOut(
        id=request.id,
        number=request.number,
        status=request.status,
        priority=request.priority,
        problem_type=problem_type.code,
        service=None,  # службу визначає маршрутизація (KAN-58)
        photos_count=0,
        created_at=request.created_at,
    )
