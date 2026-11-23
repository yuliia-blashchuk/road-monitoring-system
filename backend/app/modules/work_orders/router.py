"""HTTP-ендпоінти модуля work_orders: прийом запиту, перевірка прав (KAN-62)."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.core.access_control import AccessContext, require
from app.core.enums import RequestStatus
from app.modules.users.dependencies import SessionDep
from app.modules.work_orders import service
from app.modules.work_orders.schemas import ProgressOut, WorkOrderAssignIn, WorkOrderOut

router = APIRouter(prefix="/work-orders", tags=["work-orders"])

AssignWork = Annotated[AccessContext, Depends(require("work", "assign"))]
ViewWork = Annotated[AccessContext, Depends(require("work", "view"))]
UpdateProgress = Annotated[AccessContext, Depends(require("work", "update_progress"))]


@router.post(
    "",
    response_model=WorkOrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Призначити підрядника (адміністратор)",
    responses={
        403: {"description": "Роль не адміністратор"},
        404: {"description": "Заявку не знайдено"},
        409: {"description": "Заявка не в статусі «Прийнята» або «В роботі»"},
        422: {"description": "Підрядника немає в реєстрі, строк у минулому"},
    },
)
async def assign_contractor(
    data: WorkOrderAssignIn, session: SessionDep, ctx: AssignWork
) -> WorkOrderOut:
    """Прив'язує підрядника й кінцевий строк до заявки (UC-04, F-19). Повторний виклик
    змінює підрядника або продовжує строк; попередній підрядник одразу втрачає доступ."""
    return await service.assign(session, ctx, data)


@router.get(
    "",
    response_model=list[WorkOrderOut],
    summary="Об'єкти ремонту в моїй області дії",
    responses={403: {"description": "Роль без доступу до робіт"}},
)
async def list_work_orders(
    session: SessionDep,
    ctx: ViewWork,
    status_filter: Annotated[RequestStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WorkOrderOut]:
    """Підрядник бачить лише призначені йому об'єкти («Мої об'єкти»), служба - об'єкти
    своєї служби, адміністратор - усі. Дані водіїв не віддаються (БП-5)."""
    return await service.list_orders(session, ctx, status_filter, limit, offset)


@router.post(
    "/{request_id}/progress",
    response_model=ProgressOut,
    summary="Оновити прогрес, додати фото «після» й акт (підрядник)",
    responses={
        403: {"description": "Чужа робота або роль не підрядник"},
        404: {"description": "Заявку не знайдено"},
        409: {"description": "Заявка не в статусі «В роботі»"},
        422: {"description": "Прогрес зменшився, при 100 % немає фото «після» або акта"},
    },
)
async def update_progress(
    request_id: int,
    session: SessionDep,
    ctx: UpdateProgress,
    progress_percent: Annotated[int, Form(ge=0, le=100)],
    comment: Annotated[str | None, Form(max_length=300)] = None,
    photos: Annotated[
        list[UploadFile], File(description="До 3 фото «після»: JPEG, PNG або WebP, до 5 МБ")
    ] = [],  # noqa: B006
    act: Annotated[UploadFile | None, File(description="Акт виконаних робіт: PDF або фото")] = None,
) -> ProgressOut:
    """Форма multipart/form-data. При 100 % потрібні фото «після» й акт - тоді статус
    автоматично стає «Виконана», а «Усунена» ставить служба після перевірки (БП-6)."""
    files = []
    for upload in photos:
        item = await service.read_upload(upload)
        if item:
            files.append(item)
    comment = (comment or "").strip() or None
    return await service.update_progress(
        session, ctx, request_id, progress_percent, comment, files, await service.read_upload(act)
    )