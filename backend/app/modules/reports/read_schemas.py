"""Схеми API читання заявок: карта, «Мої звернення», картка, черга служби.

Назви полів - як у таблицях БД (request, problem_type, service, photo); координати -
lat / lng, як у фронтенді та в GET /reports/nearby.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import PhotoKind, Priority, RequestStatus


class MapReport(BaseModel):
    """Заявка на публічній карті: лише публічні поля (табл. 11), без автора й коментаря."""

    id: int
    number: int = Field(description="Номер для людей: 1001, 1002, ...")
    problem_type: str = Field(examples=["pothole"])
    problem_label: str = Field(examples=["Яма"])
    icon: str = Field(description="Іконка типу з довідника problem_type")
    color: str = Field(description="Колір маркера, наприклад #E53935")
    status: RequestStatus
    status_label: str = Field(examples=["Прийнята"])
    lat: float
    lng: float
    address: str | None
    confirmations_count: int = Field(description="Скільки водіїв натиснули «Теж бачу»")
    created_at: datetime


class MyReport(MapReport):
    """Власна заявка водія у «Моїх зверненнях»."""

    comment: str | None
    service: str | None = Field(description="Назва служби, що опрацьовує заявку")
    photos_count: int
    updated_at: datetime


class MyReportsPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[MyReport]


class PhotoInfo(BaseModel):
    id: int
    kind: PhotoKind = Field(description="before - від водія, after - від підрядника, act - акт")
    mime_type: str
    created_at: datetime
    url: str = Field(description="Адреса файлу: GET /api/v1/reports/{id}/photos/{photo_id}")


class ReportCard(BaseModel):
    """Картка заявки. Набір полів залежить від ролі (табл. 11, 13): поля, яких ролі
    бачити не можна, у відповіді відсутні."""

    id: int
    number: int
    problem_type: str
    problem_label: str
    icon: str
    color: str
    status: RequestStatus
    status_label: str
    lat: float
    lng: float
    address: str | None
    confirmations_count: int
    service: str | None
    created_at: datetime
    # Власні дані автора (водій - свої, служба й адміністратор)
    comment: str | None = None
    # Внутрішні дані служби
    priority: Priority | None = None
    copy_service: str | None = None
    deadline: date | None = None
    progress_percent: int | None = None
    reject_reason: str | None = None
    is_suspicious: bool | None = None
    is_reopened: bool | None = None
    contractor_id: int | None = None
    # Автор: служба бачить псевдонім «Заявник #…», адміністратор - id
    author: str | None = None
    author_id: int | None = None
    photos: list[PhotoInfo] = Field(default_factory=list)
    next_statuses: list[RequestStatus] = Field(
        default_factory=list, description="Куди ця роль може перевести заявку (кнопки)"
    )


class QueueItem(MapReport):
    """Рядок черги служби: найтерміновіші зверху (UC-02, табл. 18: GET /queue)."""

    priority: Priority
    comment: str | None
    author: str | None = Field(description="Псевдонім автора «Заявник #…»")
    service: str | None
    is_copy: bool = Field(description="true - служба отримала лише копію заявки")
    deadline: date | None
    progress_percent: int | None
    is_suspicious: bool
    is_reopened: bool
    next_statuses: list[RequestStatus]


class QueuePage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[QueueItem]