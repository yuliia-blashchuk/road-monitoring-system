"""Правила переходів статусів (KAN-59). Тести без БД: перевіряється лише таблиця переходів."""

import pytest

from app.core.enums import AccessRole, RequestStatus
from app.modules.reports.lifecycle import (
    FINAL_STATUSES,
    STATUS_LABELS,
    TRANSITIONS,
    check_transition,
    next_statuses,
)

S = RequestStatus
DISPATCHER, POLICE, CONTRACTOR = AccessRole.DISPATCHER, AccessRole.POLICE, AccessRole.CONTRACTOR


@pytest.mark.parametrize(
    ("current", "target", "role"),
    [
        # власні сили служби
        (S.NEW, S.ACCEPTED, DISPATCHER),
        (S.ACCEPTED, S.IN_PROGRESS, DISPATCHER),
        (S.IN_PROGRESS, S.RESOLVED, DISPATCHER),
        # підрядник
        (S.ACCEPTED, S.IN_PROGRESS, CONTRACTOR),
        (S.IN_PROGRESS, S.DONE, CONTRACTOR),
        (S.DONE, S.RESOLVED, DISPATCHER),
        # відхилення
        (S.NEW, S.REJECTED, DISPATCHER),
        (S.ACCEPTED, S.REJECTED, DISPATCHER),
        # поліція має ті самі права, що й диспетчер
        (S.NEW, S.ACCEPTED, POLICE),
        (S.DONE, S.RESOLVED, POLICE),
    ],
)
def test_allowed_transitions(current: S, target: S, role: AccessRole) -> None:
    assert check_transition(current, target, role).ok


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.NEW, S.IN_PROGRESS),  # не можна перескочити «Прийнята»
        (S.NEW, S.RESOLVED),
        (S.ACCEPTED, S.NEW),  # назад не можна
        (S.IN_PROGRESS, S.REJECTED),  # після початку робіт відхилити не можна
        (S.RESOLVED, S.IN_PROGRESS),  # закриту заявку не відкривають
        (S.REJECTED, S.ACCEPTED),
    ],
)
def test_forbidden_transitions(current: S, target: S) -> None:
    result = check_transition(current, target, DISPATCHER)
    assert not result.allowed_status
    assert "недопустимий" in result.message


def test_same_status_is_not_a_transition() -> None:
    result = check_transition(S.NEW, S.NEW, DISPATCHER)
    assert not result.allowed_status
    assert "вже має статус" in result.message


def test_contractor_cannot_resolve() -> None:
    """БП-6, UC-04 E2: «Усунена» ставить лише служба."""
    result = check_transition(S.DONE, S.RESOLVED, CONTRACTOR)
    assert result.allowed_status and not result.allowed_role


def test_dispatcher_cannot_mark_done() -> None:
    """«Виконана» означає, що підрядник здав роботу, тому її ставить лише підрядник."""
    result = check_transition(S.IN_PROGRESS, S.DONE, DISPATCHER)
    assert result.allowed_status and not result.allowed_role


@pytest.mark.parametrize("role", [AccessRole.DRIVER, AccessRole.ADMIN, AccessRole.DATA_GOVERNANCE])
def test_other_roles_change_nothing(role: AccessRole) -> None:
    """Водій, адміністратор і Data Governance статуси не змінюють (табл. 14)."""
    assert all(role not in roles for roles in TRANSITIONS.values())


def test_final_statuses_have_no_exits() -> None:
    for status in FINAL_STATUSES:
        assert next_statuses(status) == []


def test_next_statuses_for_role() -> None:
    assert next_statuses(S.NEW, DISPATCHER) == [S.ACCEPTED, S.REJECTED]
    assert next_statuses(S.IN_PROGRESS, CONTRACTOR) == [S.DONE]
    assert next_statuses(S.IN_PROGRESS, DISPATCHER) == [S.RESOLVED]


def test_every_status_has_label() -> None:
    assert set(STATUS_LABELS) == set(RequestStatus)


def test_message_lists_options() -> None:
    message = check_transition(S.NEW, S.DONE, DISPATCHER).message
    assert "«Прийнята»" in message and "«Відхилена»" in message
