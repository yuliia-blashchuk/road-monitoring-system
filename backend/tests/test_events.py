"""Внутрішня шина подій (KAN-61). Тести без БД."""

from app.core import events
from app.core.enums import RequestStatus


def make_event(**overrides) -> events.StatusChanged:
    data = {
        "request_id": 1,
        "number": 1001,
        "author_id": 7,
        "from_status": RequestStatus.NEW,
        "to_status": RequestStatus.ACCEPTED,
        "changed_by": 3,
        "service_id": 1,
    }
    return events.StatusChanged(**{**data, **overrides})


async def test_subscriber_receives_event() -> None:
    received = []

    async def handler(event: events.StatusChanged) -> None:
        received.append(event)

    events.subscribe(events.StatusChanged, handler)
    try:
        await events.publish(make_event())
    finally:
        events.unsubscribe(events.StatusChanged, handler)
    assert [e.number for e in received] == [1001]


async def test_failing_subscriber_does_not_break_others() -> None:
    """Збій одного підписника (наприклад, пошти) не зупиняє інших і не кидає помилку."""
    received = []

    async def broken(event: events.StatusChanged) -> None:
        raise RuntimeError("SMTP недоступний")

    async def working(event: events.StatusChanged) -> None:
        received.append(event)

    events.subscribe(events.StatusChanged, broken)
    events.subscribe(events.StatusChanged, working)
    try:
        await events.publish(make_event())  # помилка не виходить назовні
    finally:
        events.unsubscribe(events.StatusChanged, broken)
        events.unsubscribe(events.StatusChanged, working)
    assert len(received) == 1


async def test_subscribe_twice_is_ignored() -> None:
    calls = []

    async def handler(event: events.StatusChanged) -> None:
        calls.append(event)

    events.subscribe(events.StatusChanged, handler)
    events.subscribe(events.StatusChanged, handler)
    try:
        await events.publish(make_event())
    finally:
        events.unsubscribe(events.StatusChanged, handler)
    assert len(calls) == 1


async def test_event_without_subscribers() -> None:
    class Nobody:
        pass

    await events.publish(Nobody())  # просто нічого не відбувається