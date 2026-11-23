"""Внутрішня шина подій (п. 4.7, 4.8 проєкту).

Модуль-джерело публікує подію (наприклад, заявки - StatusChanged), а інші модулі
на неї підписуються (сповіщення). Так модуль заявок не залежить від сповіщень:
він лише повідомляє «статус змінився», а що з цим робити - вирішують підписники.

Подію публікують ПІСЛЯ commit, тому збій підписника (наприклад, пошти) не
скасовує вже збережену зміну статусу: помилка лише записується в лог.
"""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.core.enums import RequestStatus

log = logging.getLogger("roadmap.events")


@dataclass(frozen=True)
class StatusChanged:
    """Статус заявки змінено (UC-02, UC-04). Публікує модуль заявок."""

    request_id: int
    number: int
    author_id: int | None
    from_status: RequestStatus
    to_status: RequestStatus
    changed_by: int
    service_id: int | None
    comment: str | None = None
    deadline: date | None = None


Handler = Callable[[Any], Awaitable[None]]
_handlers: dict[type, list[Handler]] = defaultdict(list)


def subscribe(event_type: type, handler: Handler) -> None:
    """Підписати обробник на тип події. Повторна підписка того самого обробника ігнорується."""
    if handler not in _handlers[event_type]:
        _handlers[event_type].append(handler)


def unsubscribe(event_type: type, handler: Handler) -> None:
    if handler in _handlers[event_type]:
        _handlers[event_type].remove(handler)


async def publish(event: object) -> None:
    """Передати подію всім підписникам по черзі. Помилка одного підписника
    не зупиняє інших і не повертається тому, хто опублікував подію."""
    for handler in list(_handlers[type(event)]):
        try:
            await handler(event)
        except Exception:
            log.exception("Обробник %s не зміг опрацювати подію %r", handler.__name__, event)
