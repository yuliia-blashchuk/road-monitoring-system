"""Pydantic-схеми: що API приймає і що віддає."""

from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.core.enums import Priority, RequestStatus


class WorkOrderAssignIn(BaseModel):
    """Призначення підрядника на заявку (UC-04, кроки 1-2; F-19)."""

    request_id: int = Field(gt=0, description="Заявка, яку прийнято з дією «Потребує підрядника»")
    contractor_id: int = Field(gt=0, description="Підрядник із реєстру")
    deadline: date = Field(description="Кінцевий строк виконання робіт")
    scope: str | None = Field(
        default=None, max_length=300, description="Обсяг робіт (потрапляє в журнал аудиту)"
    )

    @field_validator("scope")
    @classmethod
    def _empty_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class WorkOrderOut(BaseModel):
    """Об'єкт ремонту. Даних про автора заявки тут немає (БП-5)."""

    id: int = Field(description="id заявки (об'єкт ремонту прив'язаний до заявки)")
    number: int
    status: RequestStatus
    priority: Priority
    problem_type: str
    address: str | None
    service_id: int | None
    contractor_id: int | None
    contractor_name: str | None
    deadline: date | None
    progress_percent: int | None
    is_overdue: bool = Field(description="Строк минув, а роботи не завершено (UC-04, A1)")


class ProgressOut(BaseModel):
    """Результат оновлення прогресу (UC-06)."""

    id: int
    number: int
    status: RequestStatus
    progress_percent: int
    photos_added: int
    act_attached: bool
    submitted: bool = Field(description="true - при 100 % роботи здано, статус «Виконана»")