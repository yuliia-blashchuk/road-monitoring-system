"""HTTP-ендпоінти дедуплікації та «Теж бачу» (F-21, F-22, UC-01 A1).

GET  /reports/nearby        - схожі активні заявки в радіусі 30 м (перед створенням заявки);
POST /reports/{id}/confirm  - «Теж бачу».

Права: report.create і report.confirm є лише у водія (табл. 14). Область OWN для confirm
означає «підтвердження від власного імені», тому автора заявки тут не порівнюємо з
поточним користувачем через ensure_target - водій підтверджує чужу заявку.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.access_control import AccessContext, require
from app.core.openapi import errors
from app.modules.dedup import service
from app.modules.dedup.schemas import ConfirmResult, NearbyReport
from app.modules.users.dependencies import SessionDep

router = APIRouter(prefix="/reports", tags=["dedup"], responses=errors(401, 403))

CreateReport = Annotated[AccessContext, Depends(require("report", "create"))]
ConfirmReport = Annotated[AccessContext, Depends(require("report", "confirm"))]

ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "closed": status.HTTP_409_CONFLICT,
    "own": status.HTTP_409_CONFLICT,
    "duplicate": status.HTTP_409_CONFLICT,
}


@router.get(
    "/nearby",
    response_model=list[NearbyReport],
    summary="Схожі заявки поруч (радіус 30 м) перед створенням нової",
)
async def nearby_reports(
    session: SessionDep,
    _: CreateReport,
    lat: Annotated[float, Query(ge=-90, le=90, description="Широта точки")],
    lng: Annotated[float, Query(ge=-180, le=180, description="Довгота точки")],
    problem_type_id: Annotated[int, Query(gt=0, description="Тип проблеми")],
) -> list[NearbyReport]:
    rows = await service.find_duplicates(session, lat=lat, lng=lng, problem_type_id=problem_type_id)
    return [
        NearbyReport(
            id=row.request.id,
            number=row.request.number,
            problem_type_id=row.request.problem_type_id,
            status=row.request.status,
            confirmations_count=row.request.confirmations_count,
            address=row.request.address,
            lat=row.lat,
            lng=row.lng,
            distance_m=round(row.distance_m, 1),
            created_at=row.request.created_at,
        )
        for row in rows
    ]


@router.post(
    "/{request_id}/confirm",
    response_model=ConfirmResult,
    summary="«Теж бачу»: підтвердити існуючу заявку",
    responses=errors(
        404,
        409,
        e404="Заявку не знайдено",
        e409="Заявку закрито, вона власна або вже підтверджена цим водієм",
    ),
)
async def confirm_report(
    session: SessionDep,
    ctx: ConfirmReport,
    request_id: Annotated[int, Path(gt=0)],
) -> ConfirmResult:
    try:
        result = await service.confirm(session, request_id, ctx.user)
    except service.ConfirmError as exc:
        raise HTTPException(ERROR_STATUS[exc.code], exc.message) from exc
    return ConfirmResult(
        request_id=result.request_id,
        confirmations_count=result.confirmations_count,
        priority_raised=result.priority_raised,
    )
