"""HTTP-ендпоінти модуля reports: прийом запиту, перевірка прав."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, status

from app.core.access_control import AccessContext, require
from app.modules.reports import service
from app.modules.reports.schemas import ReportCreatedOut, ReportCreateForm
from app.modules.users.dependencies import SessionDep

router = APIRouter(prefix="/reports", tags=["reports"])

CreateReport = Annotated[AccessContext, Depends(require("report", "create"))]


@router.post(
    "",
    response_model=ReportCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Створити заявку (водій)",
    responses={
        403: {"description": "Роль не водій"},
        422: {"description": "Помилка в полях: тип, координати, коментар, межі міста"},
    },
)
async def create_report(
    data: Annotated[ReportCreateForm, Form()],
    session: SessionDep,
    ctx: CreateReport,
) -> ReportCreatedOut:
    """Форма multipart/form-data. Створює заявку зі статусом «Нова» і перший запис
    історії статусів в одній транзакції."""
    return await service.create_report(session, ctx.user, data)
