"""Pydantic-схеми модуля dedup: що API приймає і що віддає.

Схожа заявка віддається лише з публічними полями (табл. 13): без автора й коментаря,
бо її бачить інший водій.
"""

from datetime import datetime

from pydantic import BaseModel

from app.core.enums import RequestStatus


class NearbyReport(BaseModel):
    id: int
    number: int
    problem_type_id: int
    status: RequestStatus
    confirmations_count: int
    address: str | None
    lat: float
    lng: float
    distance_m: float
    created_at: datetime


class ConfirmResult(BaseModel):
    request_id: int
    confirmations_count: int
    # Пріоритет - внутрішнє поле, тому тут лише факт підвищення без значення.
    priority_raised: bool
