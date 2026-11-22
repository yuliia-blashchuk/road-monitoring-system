"""Схеми API журналу аудиту."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    actor_id: int | None
    actor_role: str | None
    action: str
    entity_type: str | None
    entity_id: int | None
    result: str
    old_value: dict | None
    new_value: dict | None
    ip: str | None = Field(default=None, description="IP-адреса, з якої зроблено запит")
    correlation_id: UUID | None = Field(
        default=None, description="Ідентифікатор запиту (X-Request-ID): усі записи одного запиту"
    )

    @field_validator("ip", mode="before")
    @classmethod
    def _ip_to_str(cls, v: Any) -> str | None:
        if isinstance(v, IPv4Address | IPv6Address):
            return str(v)
        return v


class AuditPage(BaseModel):
    """Сторінка журналу: записи від новіших до старіших і загальна кількість за фільтром."""

    total: int = Field(description="Скільки записів відповідає фільтрам загалом")
    limit: int
    offset: int
    items: list[AuditLogOut]


class AuditActionCount(BaseModel):
    """Тип події і скільки разів вона трапилась - для списку фільтра в журналі."""

    action: str
    count: int
