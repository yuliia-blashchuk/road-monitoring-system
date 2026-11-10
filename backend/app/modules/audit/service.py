"""Запис подій у журнал аудиту (п. 3.8, табл. 18).

Правила:
- запис робиться в тій самій транзакції, що й зміна (викликач робить commit);
- у журнал не пишуться паролі й токени, email маскується (m***@gmail.com);
- IP і correlation_id беруться з контексту запиту автоматично.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import client_ip_var, correlation_id_var
from app.modules.audit.models import AuditLog

FORBIDDEN_KEYS = {"password", "password_hash", "token", "access_token"}


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def _clean(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {k: v for k, v in value.items() if k not in FORBIDDEN_KEYS}


def record(
    session: AsyncSession,
    action: str,
    *,
    actor_id: int | None = None,
    actor_role: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    result: str = "success",
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> AuditLog:
    """Додає запис AuditLog у сесію (без commit)."""
    entry = AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        result=result,
        old_value=_clean(old_value),
        new_value=_clean(new_value),
        ip=client_ip_var.get(),
        correlation_id=correlation_id_var.get(),
    )
    session.add(entry)
    return entry
