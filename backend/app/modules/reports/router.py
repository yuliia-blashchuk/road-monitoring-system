"""HTTP-ендпоінти модуля reports: прийом запиту, перевірка прав."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.access_control import AccessContext, require
from app.modules.reports import service
from app.modules.reports.photos import MAX_PHOTO_BYTES
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
