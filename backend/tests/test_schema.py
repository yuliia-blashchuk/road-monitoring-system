"""Перевірка схеми БД і довідників (KAN-48)."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models import AccessPolicy, ProblemType, Service
from app.modules.routing.models import RoutingRule
from app.modules.users.models import Role

EXPECTED_TABLES = {
    "role",
    "users",
    "consent",
    "service",
    "problem_type",
    "routing_rule",
    "request",
    "photo",
    "confirmation",
    "status_history",
    "audit_log",
    "contractor",
    "notification",
    "access_policy",
    "city_boundary",
}

LVIV_CENTER = "SRID=4326;POINT(24.0297 49.8397)"


async def _make_driver(db: AsyncSession, email: str = "driver@test.ua") -> int:
    return (
        await db.execute(
            text(
                "INSERT INTO users (email, password_hash, full_name, role_id) "
                "SELECT :email, 'x', 'Тест', id FROM role WHERE code = 'driver' RETURNING id"
            ),
            {"email": email},
        )
    ).scalar_one()


async def _make_request(db: AsyncSession, author_id: int, **extra: str) -> int:
    cols = ", ".join(["author_id", "problem_type_id", "location", *extra])
    vals = ", ".join([":author", "(SELECT id FROM problem_type WHERE code='pothole')", ":loc"])
    vals += "".join(f", :{k}" for k in extra)
    return (
        await db.execute(
            text(f"INSERT INTO request ({cols}) VALUES ({vals}) RETURNING id"),
            {"author": author_id, "loc": LVIV_CENTER, **extra},
        )
    ).scalar_one()


async def test_all_tables_exist(db: AsyncSession) -> None:
    rows = await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    assert EXPECTED_TABLES <= {r[0] for r in rows}


async def test_reference_data_seeded(db: AsyncSession) -> None:
    roles = set((await db.execute(select(Role.code))).scalars())
    assert roles == {"driver", "operator", "dispatcher", "contractor", "admin", "data_governance"}
    assert await db.scalar(select(func.count()).select_from(ProblemType)) == 6
    assert await db.scalar(select(func.count()).select_from(Service)) == 3
    assert await db.scalar(select(func.count()).select_from(AccessPolicy)) > 0


async def test_every_problem_type_has_routing_rule(db: AsyncSession) -> None:
    """DQ-12: для кожного типу є правило маршрутизації з початковим пріоритетом."""
    missing = await db.execute(
        select(ProblemType.code).where(
            ~select(RoutingRule.id).where(RoutingRule.problem_type_id == ProblemType.id).exists()
        )
    )
    assert missing.scalars().all() == []


async def _rule(db: AsyncSession, code: str) -> list[tuple[str, str | None, str]]:
    rows = await db.execute(
        text(
            "SELECT s.name, cs.name, r.initial_priority FROM routing_rule r "
            "JOIN problem_type pt ON pt.id = r.problem_type_id "
            "JOIN service s ON s.id = r.service_id "
            "LEFT JOIN service cs ON cs.id = r.copy_service_id "
            "WHERE pt.code = :code ORDER BY s.name"
        ),
        {"code": code},
    )
    return [(a, b, str(c)) for a, b, c in rows]


async def test_accident_goes_to_police_critical(db: AsyncSession) -> None:
    """KAN-58: ДТП -> поліція, критичний, копія комунальній службі."""
    [(service, copy, priority)] = await _rule(db, "accident")
    assert "поліція" in service and copy is not None and "Комунальна" in copy
    assert priority == "critical"


async def test_obstacle_police_with_communal_copy(db: AsyncSession) -> None:
    """KAN-58: перешкода -> поліція + копія комунальній службі."""
    [(service, copy, priority)] = await _rule(db, "obstacle")
    assert "поліція" in service and "Комунальна" in copy and priority == "high"


async def test_pothole_rule_for_each_district(db: AsyncSession) -> None:
    rules = await _rule(db, "pothole")
    assert len(rules) == 2
    assert all(copy is None and priority == "medium" for _, copy, priority in rules)


async def test_district_zones_split_city(db: AsyncSession) -> None:
    """F-23: точка належить зоні рівно однієї комунальної служби."""
    for lon in (23.95, 24.10):
        names = await db.scalars(
            text(
                "SELECT name FROM service WHERE kind = 'communal' AND ST_Contains(zone, "
                "ST_SetSRID(ST_MakePoint(:lon, 49.84), 4326))"
            ),
            {"lon": lon},
        )
        assert len(names.all()) == 1


async def test_point_inside_city(db: AsyncSession) -> None:
    inside = await db.scalar(
        text("SELECT ST_Contains(geom, ST_GeomFromEWKT(:p)) FROM city_boundary"),
        {"p": LVIV_CENTER},
    )
    outside = await db.scalar(
        text(
            "SELECT ST_Contains(geom, ST_GeomFromEWKT('SRID=4326;POINT(30.52 50.45)')) "
            "FROM city_boundary"
        )
    )
    assert inside is True and outside is False


async def test_request_gets_number_and_defaults(db: AsyncSession) -> None:
    req_id = await _make_request(db, await _make_driver(db))
    row = (
        await db.execute(
            text("SELECT number, status, priority, confirmations_count FROM request WHERE id=:i"),
            {"i": req_id},
        )
    ).one()
    assert row.number >= 1001
    assert (str(row.status), str(row.priority), row.confirmations_count) == ("new", "medium", 0)


async def test_reject_requires_reason(db: AsyncSession) -> None:
    """БП-3: статус rejected без причини заборонений CHECK-обмеженням."""
    author = await _make_driver(db)
    with pytest.raises(IntegrityError):
        await _make_request(db, author, status="rejected")


async def test_comment_max_300(db: AsyncSession) -> None:
    author = await _make_driver(db)
    with pytest.raises(DBAPIError):
        await _make_request(db, author, comment="x" * 301)


async def test_progress_between_0_and_100(db: AsyncSession) -> None:
    author = await _make_driver(db)
    with pytest.raises(IntegrityError):
        await _make_request(db, author, progress_percent=101)


async def test_email_unique(db: AsyncSession) -> None:
    await _make_driver(db, "same@test.ua")
    with pytest.raises(IntegrityError):
        await _make_driver(db, "same@test.ua")


async def test_confirmation_once_per_driver(db: AsyncSession) -> None:
    """DQ-07: один водій підтверджує заявку один раз."""
    author = await _make_driver(db)
    req = await _make_request(db, author)
    sql = text("INSERT INTO confirmation (request_id, user_id) VALUES (:r, :u)")
    await db.execute(sql, {"r": req, "u": author})
    with pytest.raises(IntegrityError):
        await db.execute(sql, {"r": req, "u": author})


@pytest.mark.parametrize("table", ["audit_log", "status_history"])
async def test_logs_are_append_only(db: AsyncSession, table: str) -> None:
    """QR-13: журнали лише доповнюються - тригер забороняє UPDATE і DELETE."""
    if table == "audit_log":
        await db.execute(text("INSERT INTO audit_log (action) VALUES ('TEST')"))
    else:
        req = await _make_request(db, await _make_driver(db))
        await db.execute(
            text("INSERT INTO status_history (request_id, to_status) VALUES (:r, 'new')"),
            {"r": req},
        )
    await db.commit()

    with pytest.raises(DBAPIError, match="лише для додавання"):
        await db.execute(text(f"UPDATE {table} SET id = id"))
    await db.rollback()
    with pytest.raises(DBAPIError, match="лише для додавання"):
        await db.execute(text(f"DELETE FROM {table}"))
    await db.rollback()
