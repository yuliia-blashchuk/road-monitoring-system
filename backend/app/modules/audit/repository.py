"""Запити до БД цього модуля. Інші модулі сюди напряму не звертаються."""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


@dataclass(frozen=True)
class AuditFilters:
    """Фільтри перегляду журналу. None - фільтр не застосовується."""

    action: str | None = None
    actor_id: int | None = None
    actor_role: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    result: str | None = None
    correlation_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    def used(self) -> dict[str, Any]:
        """Лише задані фільтри - їх записуємо в AUDIT_VIEWED."""
        return {
            k: (v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, UUID) else v)
            for k, v in asdict(self).items()
            if v is not None
        }


def _apply(query: Select, f: AuditFilters) -> Select:
    exact = {
        AuditLog.action: f.action,
        AuditLog.actor_id: f.actor_id,
        AuditLog.actor_role: f.actor_role,
        AuditLog.entity_type: f.entity_type,
        AuditLog.entity_id: f.entity_id,
        AuditLog.result: f.result,
        AuditLog.correlation_id: f.correlation_id,
    }
    for column, value in exact.items():
        if value is not None:
            query = query.where(column == value)
    if f.date_from is not None:
        query = query.where(AuditLog.created_at >= f.date_from)
    if f.date_to is not None:
        query = query.where(AuditLog.created_at <= f.date_to)
    return query


async def search(
    session: AsyncSession, filters: AuditFilters, limit: int, offset: int
) -> tuple[list[AuditLog], int]:
    """Записи за фільтрами (новіші спершу) і загальна кількість для пагінації."""
    total = await session.scalar(_apply(select(func.count()).select_from(AuditLog), filters))
    rows = await session.scalars(
        _apply(select(AuditLog), filters)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0
