"""Pydantic-схеми заявки: що API приймає і що віддає.

Схема форми створення заявки публікується як JSON Schema в OpenAPI (/docs),
тому фронтенд і тести перевіряються за тим самим описом полів (KAN-57, DQ-01–DQ-05).
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.enums import Priority, RequestStatus

COMMENT_MAX = 300


class ReportCreateForm(BaseModel):
    """Поля форми «Повідомити про проблему» (multipart/form-data)."""

    problem_type: str = Field(
        min_length=1,
        max_length=50,
        description="Код типу проблеми з GET /problem-types",
        examples=["pothole"],
    )
    latitude: float = Field(ge=-90, le=90, description="Широта WGS84", examples=[49.8397])
    longitude: float = Field(ge=-180, le=180, description="Довгота WGS84", examples=[24.0297])
    comment: str | None = Field(
        default=None,
        max_length=COMMENT_MAX,
        description="Необов'язковий коментар, до 300 символів",
    )
    address: str | None = Field(default=None, max_length=255)
    device_created_at: datetime | None = Field(
        default=None,
        description="Час створення на пристрої для офлайн-заявки (DQ-09)",
    )
    media_sharing_consent: bool = Field(
        default=False,
        description=(
            "Згода передати службі фото й коментар (media_sharing). Потрібна, якщо є фото "
            "або коментар; true зберігає згоду, якщо її ще немає"
        ),
    )

    @field_validator("problem_type")
    @classmethod
    def _normalize_type(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("comment", "address")
    @classmethod
    def _empty_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ReportCreatedOut(BaseModel):
    """Відповідь водієві: номер заявки, статус і служба (UC-01, постумова)."""

    id: int
    number: int
    status: RequestStatus
    priority: Priority
    problem_type: str
    service: str | None = Field(description="Назва служби; null - заявку отримує адміністратор")
    photos_count: int
    created_at: datetime
