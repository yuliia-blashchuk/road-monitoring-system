"""Схеми API журналу аудиту."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
