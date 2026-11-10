"""Перегляд журналу аудиту (адміністратор і Data Governance). Сам перегляд теж
фіксується подією AUDIT_VIEWED (п. 3.8)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.access_control import AccessContext, require
from app.modules.audit import service as audit
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditLogOut
from app.modules.users.dependencies import SessionDep

router = APIRouter(prefix="/audit", tags=["audit"])

ViewAudit = Annotated[AccessContext, Depends(require("audit", "view"))]


@router.get("", response_model=list[AuditLogOut], summary="Журнал аудиту")
async def list_audit(
    session: SessionDep,
    ctx: ViewAudit,
    action: str | None = None,
    actor_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        query = query.where(AuditLog.action == action)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    rows = list(await session.scalars(query))

    audit.record(
        session,
        "AUDIT_VIEWED",
        actor_id=ctx.user.id,
        actor_role=ctx.role.value,
        new_value={"action": action, "actor_id": actor_id, "limit": limit},
    )
    await session.commit()
    return rows
