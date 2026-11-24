"""Перегляд журналу аудиту (адміністратор і Data Governance). Сам перегляд теж
фіксується подією AUDIT_VIEWED (п. 3.8)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.access_control import AccessContext, require
from app.core.openapi import errors
from app.modules.audit import repository as repo
from app.modules.audit import service as audit
from app.modules.audit.schemas import AuditActionCount, AuditLogOut, AuditPage
from app.modules.users.dependencies import SessionDep

router = APIRouter(prefix="/audit", tags=["audit"], responses=errors(401, 403))

ViewAudit = Annotated[AccessContext, Depends(require("audit", "view"))]


@router.get(
    "",
    response_model=AuditPage,
    summary="Журнал аудиту з фільтрами",
    responses={
        403: {"description": "Роль не адміністратор і не Data Governance"},
        422: {"description": "Неправильний фільтр, наприклад date_from пізніше за date_to"},
    },
)
async def list_audit(
    session: SessionDep,
    ctx: ViewAudit,
    action: Annotated[str | None, Query(description="STATUS_CHANGED, LOGIN_FAILED, ...")] = None,
    actor_id: Annotated[int | None, Query(description="Хто виконав дію")] = None,
    actor_role: Annotated[str | None, Query(description="driver, dispatcher, admin, ...")] = None,
    entity_type: Annotated[str | None, Query(description="request, user, ...")] = None,
    entity_id: Annotated[int | None, Query(description="id запису, наприклад заявки")] = None,
    result: Annotated[str | None, Query(description="success, failure або denied")] = None,
    correlation_id: Annotated[UUID | None, Query(description="Усі записи одного запиту")] = None,
    date_from: Annotated[datetime | None, Query(description="Від (включно), ISO 8601")] = None,
    date_to: Annotated[datetime | None, Query(description="До (включно), ISO 8601")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    """Записи від новіших до старіших. Наприклад, усі зміни заявки 5:
    `?entity_type=request&entity_id=5`; відмови в доступі: `?action=ACCESS_DENIED`."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"loc": ["query", "date_from"], "msg": "date_from пізніше за date_to"}],
        )
    filters = repo.AuditFilters(
        action=action.strip().upper() if action else None,
        actor_id=actor_id,
        actor_role=actor_role,
        entity_type=entity_type,
        entity_id=entity_id,
        result=result,
        correlation_id=correlation_id,
        date_from=date_from,
        date_to=date_to,
    )
    rows, total = await repo.search(session, filters, limit, offset)
    page = AuditPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[AuditLogOut.model_validate(row) for row in rows],
    )

    audit.record(
        session,
        "AUDIT_VIEWED",
        actor_id=ctx.user.id,
        actor_role=ctx.role.value,
        new_value={**filters.used(), "limit": limit, "offset": offset, "total": total},
    )
    await session.commit()
    return page


@router.get(
    "/actions",
    response_model=list[AuditActionCount],
    summary="Типи подій у журналі (для фільтра)",
)
async def list_actions(session: SessionDep, ctx: ViewAudit) -> list[AuditActionCount]:
    """Які дії є в журналі і скільки їх: STATUS_CHANGED, ACCESS_DENIED, LOGIN_FAILED тощо.
    Повертає лише назви й кількість, без самих записів, тому окремо не журналюється."""
    return [
        AuditActionCount(action=action, count=count)
        for action, count in await repo.action_counts(session)
    ]
