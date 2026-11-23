"""Схеми API сповіщень."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int | None = Field(description="Заявка, якої стосується сповіщення")
    type: str = Field(examples=["STATUS_CHANGED"])
    message: str
    is_read: bool
    created_at: datetime


class NotificationPage(BaseModel):
    """Стрічка сповіщень: новіші спершу."""

    total: int = Field(description="Скільки сповіщень за фільтром")
    unread: int = Field(description="Скільки непрочитаних загалом (для лічильника на дзвіночку)")
    limit: int
    offset: int
    items: list[NotificationOut]


class ReadAllOut(BaseModel):
    updated: int = Field(description="Скільки сповіщень позначено прочитаними")
