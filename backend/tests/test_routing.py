"""Маршрутизація заявки (KAN-58, F-10, F-23, DQ-12)."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Priority
from app.modules.admin.models import ProblemType
from app.modules.routing.service import route

WEST_POINT = (49.84, 23.98)  # Залізничний район (демо-зона)
EAST_POINT = (49.84, 24.08)  # Шевченківський район (демо-зона)
WEST = "Комунальна служба Залізничного району (демо)"
EAST = "Комунальна служба Шевченківського району (демо)"
POLICE = "Дорожня поліція (демо)"


async def type_id(db: AsyncSession, code: str) -> int:
    return await db.scalar(select(ProblemType.id).where(ProblemType.code == code))


@pytest.mark.parametrize(("point", "expected"), [(WEST_POINT, WEST), (EAST_POINT, EAST)])
async def test_pothole_goes_to_district_service(
    db: AsyncSession, point: tuple[float, float], expected: str
) -> None:
    """TC-UC01-13: служба визначається за геозоною."""
    result = await route(db, await type_id(db, "pothole"), *point)
    assert result.service.name == expected
    assert result.copy_service is None
    assert result.priority == Priority.MEDIUM
    assert result.rule_id is not None


@pytest.mark.parametrize(("point", "copy"), [(WEST_POINT, WEST), (EAST_POINT, EAST)])
async def test_accident_police_critical_with_district_copy(
    db: AsyncSession, point: tuple[float, float], copy: str
) -> None:
    """ДТП -> поліція, критичний; копію отримує комунальна служба району точки."""
    result = await route(db, await type_id(db, "accident"), *point)
    assert result.service.name == POLICE
    assert result.copy_service.name == copy
    assert result.priority == Priority.CRITICAL


async def test_obstacle_police_with_communal_copy(db: AsyncSession) -> None:
    result = await route(db, await type_id(db, "obstacle"), *EAST_POINT)
    assert result.service.name == POLICE
    assert result.copy_service.name == EAST
    assert result.priority == Priority.HIGH


@pytest.mark.parametrize(
    ("code", "priority"),
    [("damaged_surface", Priority.LOW), ("traffic_light", Priority.HIGH), ("other", Priority.LOW)],
)
async def test_initial_priority_from_rule(db: AsyncSession, code: str, priority: Priority) -> None:
    assert (await route(db, await type_id(db, code), *WEST_POINT)).priority == priority


async def test_no_rule_means_no_service(db: AsyncSession) -> None:
    """DQ-12: тип без правила - служба не визначена, заявку отримує адміністратор."""
    db.add(ProblemType(code="test_no_rule", name="Без правила", icon="x", color="#000000"))
    await db.flush()
    try:
        result = await route(db, await type_id(db, "test_no_rule"), *WEST_POINT)
        assert result.service is None and result.rule_id is None
        assert result.priority == Priority.MEDIUM
    finally:
        await db.rollback()


async def test_inactive_rule_ignored(db: AsyncSession) -> None:
    pothole = await type_id(db, "pothole")
    await db.execute(
        text("UPDATE routing_rule SET is_active = false WHERE problem_type_id = :t"),
        {"t": pothole},
    )
    try:
        assert (await route(db, pothole, *WEST_POINT)).service is None
    finally:
        await db.rollback()


async def test_inactive_service_ignored(db: AsyncSession) -> None:
    await db.execute(text("UPDATE service SET is_active = false WHERE name = :n"), {"n": WEST})
    try:
        result = await route(db, await type_id(db, "accident"), *WEST_POINT)
        assert result.service.name == POLICE
        assert result.copy_service is None  # у районі немає активної комунальної служби
    finally:
        await db.rollback()
