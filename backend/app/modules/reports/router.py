"""HTTP-ендпоінти модуля reports: прийом запиту, перевірка прав."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.access_control import AccessContext, require
from app.modules.reports import service
from app.modules.reports.photos import MAX_PHOTO_BYTES
from app.modules.reports.schemas import (
    ReportCreatedOut,
    ReportCreateForm,
    ReportHistoryOut,
    StatusChangeIn,
    StatusChangeOut,
)
from app.modules.users.dependencies import SessionDep

router = APIRouter(prefix="/reports", tags=["reports"])

CreateReport = Annotated[AccessContext, Depends(require("report", "create"))]
ChangeStatus = Annotated[AccessContext, Depends(require("report", "change_status"))]
ViewHistory = Annotated[AccessContext, Depends(require("report", "view_history"))]


@router.post(
    "",
    response_model=ReportCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Створити заявку (водій)",
    responses={
        403: {"description": "Роль не водій або немає згоди personal_data"},
        422: {"description": "Помилка в полях: тип, координати, коментар, межі міста"},
        429: {"description": "Понад 10 заявок на годину з акаунта"},
    },
)
async def create_report(
    data: Annotated[ReportCreateForm, Form()],
    session: SessionDep,
    ctx: CreateReport,
    photos: Annotated[
        list[UploadFile],
        File(description="До 3 фото: JPEG, PNG або WebP, кожне до 5 МБ"),
    ] = [],  # noqa: B006 - FastAPI створює новий список для кожного запиту
) -> ReportCreatedOut:
    """Форма multipart/form-data. Створює заявку зі статусом «Нова», перший запис
    історії статусів і фото в одній транзакції."""
    # Читаємо на 1 байт більше за ліміт, щоб не тримати в пам'яті завеликі файли.
    files = [(f.filename or "photo", await f.read(MAX_PHOTO_BYTES + 1)) for f in photos]
    return await service.create_report(session, ctx.user, data, files)


@router.patch(
    "/{request_id}/status",
    response_model=StatusChangeOut,
    summary="Змінити статус заявки (служба, підрядник)",
    responses={
        403: {"description": "Роль не може змінювати статус, чужа заявка або чужий перехід"},
        404: {"description": "Заявку не знайдено"},
        409: {"description": "Перехід недопустимий з поточного статусу"},
        422: {"description": "Немає причини відхилення, строк у минулому"},
    },
)
async def change_status(
    request_id: int, data: StatusChangeIn, session: SessionDep, ctx: ChangeStatus
) -> StatusChangeOut:
    """Допустимі переходи: «Нова» → «Прийнята» → «В роботі» → «Усунена» (служба)
    або «В роботі» → «Виконана» (підрядник) → «Усунена» (служба); «Нова» і
    «Прийнята» → «Відхилена» з обов'язковою причиною. Кожна зміна пишеться в
    історію статусів і журнал аудиту."""
    return await service.change_status(session, ctx, request_id, data)


@router.get(
    "/{request_id}/history",
    response_model=ReportHistoryOut,
    summary="Історія статусів заявки (таймлайн)",
    responses={
        403: {"description": "Чужа заявка або роль без доступу"},
        404: {"description": "Заявку не знайдено"},
    },
)
async def report_history(
    request_id: int, session: SessionDep, ctx: ViewHistory
) -> ReportHistoryOut:
    """Усі зміни статусу від створення заявки: з якого, на який, коментар, час.
    Водій бачить таймлайн своїх заявок без даних про те, хто з працівників змінив статус."""
    return await service.report_history(session, ctx, request_id)
