"""Ендпоінти читання заявок (табл. 18): карта, «Мої звернення», картка, фото, черга.

Фронтенд бере дані звідси замість демо-даних (data/mapEvents.ts).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.access_control import AccessContext, access_role, require
from app.core.enums import AccessRole, RequestStatus
from app.modules.reports import read_service as service
from app.modules.reports.read_schemas import MapReport, MyReportsPage, QueuePage, ReportCard
from app.modules.users.dependencies import CurrentUser, SessionDep

router = APIRouter(prefix="/reports", tags=["reports"])
queue_router = APIRouter(prefix="/queue", tags=["reports"])

ViewOwn = Annotated[AccessContext, Depends(require("report", "view_own"))]
ViewInternal = Annotated[AccessContext, Depends(require("report", "view_internal"))]
ViewPhoto = Annotated[AccessContext, Depends(require("photo", "view_original"))]


async def view_report(request: Request, user: CurrentUser, session: SessionDep) -> AccessContext:
    """Картку водій відкриває за політикою view_own (лише свої), решта - view_internal."""
    action = "view_own" if access_role(user) == AccessRole.DRIVER else "view_internal"
    return await require("report", action)(request, user, session)


ViewCard = Annotated[AccessContext, Depends(view_report)]


@router.get("", response_model=list[MapReport], summary="Заявки на карті (публічно)")
async def map_reports(
    session: SessionDep,
    bbox: Annotated[
        str | None,
        Query(
            description="Видима частина карти: мін_довгота,мін_широта,макс_довгота,макс_широта",
            examples=["23.92,49.80,24.14,49.88"],
        ),
    ] = None,
    type: Annotated[
        list[str] | None,
        Query(description="Тип проблеми, можна кілька: ?type=pothole&type=accident"),
    ] = None,
    status: Annotated[
        list[RequestStatus] | None,
        Query(description="Статус, можна кілька. За замовчуванням - усі незакриті"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[MapReport]:
    """Без входу в систему. Лише публічні поля: без автора, коментаря й фото (табл. 11).
    Усунені й відхилені заявки на карті не показуються (БП-4)."""
    return await service.map_reports(session, status, type, bbox, limit)


@router.get("/my", response_model=MyReportsPage, summary="Мої звернення (водій)")
async def my_reports(
    session: SessionDep,
    ctx: ViewOwn,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MyReportsPage:
    """Усі заявки водія, новіші спершу, з будь-яким статусом."""
    return await service.my_reports(session, ctx, limit, offset)


@router.get(
    "/{request_id}",
    response_model=ReportCard,
    response_model_exclude_unset=True,
    summary="Картка заявки",
    responses={
        403: {"description": "Чужа заявка або роль без доступу"},
        404: {"description": "Заявку не знайдено"},
    },
)
async def report_card(request_id: int, session: SessionDep, ctx: ViewCard) -> ReportCard:
    """Водій - лише свою заявку; служба - заявки своєї служби (зокрема копії);
    підрядник - призначені йому; адміністратор - усі. Поля залежать від ролі."""
    return await service.report_card(session, ctx, request_id)


@router.get(
    "/{request_id}/photos/{photo_id}",
    summary="Файл фото або акта",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}, "image/png": {}, "application/pdf": {}}},
        403: {"description": "Немає доступу до фото цієї заявки"},
        404: {"description": "Фото не знайдено"},
    },
)
async def photo_file(
    request_id: int, photo_id: int, session: SessionDep, ctx: ViewPhoto
) -> Response:
    data, mime_type = await service.photo_file(session, ctx, request_id, photo_id)
    return Response(content=data, media_type=mime_type)


@queue_router.get("", response_model=QueuePage, summary="Черга заявок служби")
async def service_queue(
    session: SessionDep,
    ctx: ViewInternal,
    status: Annotated[
        list[RequestStatus] | None,
        Query(description="Статус, можна кілька. За замовчуванням - усі незакриті"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QueuePage:
    """Спершу критичні, потім високий, середній, низький пріоритет; усередині - старіші
    раніше (UC-02). Служба бачить і заявки, де вона отримала копію (is_copy)."""
    return await service.service_queue(session, ctx, status, limit, offset)
