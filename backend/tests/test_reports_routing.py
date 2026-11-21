"""Маршрутизація під час створення заявки (KAN-58, TC-UC01-12, TC-UC01-13)."""

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models import Service
from app.modules.audit.models import AuditLog
from app.modules.reports.models import Request
from tests.factories import auth, make_driver

URL = "/api/v1/reports"
WEST = {"latitude": 49.84, "longitude": 23.98}
EAST = {"latitude": 49.84, "longitude": 24.08}
WEST_NAME = "Комунальна служба Залізничного району (демо)"
EAST_NAME = "Комунальна служба Шевченківського району (демо)"
POLICE = "Дорожня поліція (демо)"


async def create(client: AsyncClient, db: AsyncSession, problem_type: str, point: dict) -> dict:
    driver = await make_driver(db, email=f"{problem_type}{point['longitude']}@test.ua")
    response = await client.post(
        URL, data={"problem_type": problem_type, **point}, headers=auth(driver)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def service_name(db: AsyncSession, service_id: int | None) -> str | None:
    return await db.scalar(select(Service.name).where(Service.id == service_id))


async def test_two_points_two_district_services(client: AsyncClient, db: AsyncSession) -> None:
    """TC-UC01-13: кожна заявка потрапила лише в чергу служби своєї геозони."""
    west = await create(client, db, "pothole", WEST)
    east = await create(client, db, "pothole", EAST)
    assert west["service"] == WEST_NAME and east["service"] == EAST_NAME

    request = await db.get(Request, east["id"])
    assert await service_name(db, request.service_id) == EAST_NAME
    assert request.copy_service_id is None
    assert request.priority == "medium"


async def test_accident_to_police_and_district(client: AsyncClient, db: AsyncSession) -> None:
    """TC-UC01-12: аварію бачать і дорожня поліція, і комунальна служба району."""
    body = await create(client, db, "accident", EAST)
    assert body["service"] == POLICE
    assert body["copy_service"] == EAST_NAME
    assert body["priority"] == "critical"


async def test_obstacle_to_police_with_copy(client: AsyncClient, db: AsyncSession) -> None:
    body = await create(client, db, "obstacle", WEST)
    assert (body["service"], body["copy_service"], body["priority"]) == (POLICE, WEST_NAME, "high")


async def test_routing_written_to_audit(client: AsyncClient, db: AsyncSession) -> None:
    """Табл. 18: у REPORT_CREATED записано службу і правило маршрутизації."""
    body = await create(client, db, "obstacle", WEST)
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "REPORT_CREATED"))
    request = await db.get(Request, body["id"])
    assert entry.new_value["service_id"] == request.service_id
    assert entry.new_value["copy_service_id"] == request.copy_service_id
    assert entry.new_value["priority"] == "high"
    assert entry.new_value["routing_rule_id"] is not None


async def test_type_without_rule_goes_to_admin(client: AsyncClient, db: AsyncSession) -> None:
    """DQ-12: правила немає - служба не визначена, заявку отримує адміністратор."""
    off = "UPDATE routing_rule SET is_active = :on WHERE problem_type_id = "
    off += "(SELECT id FROM problem_type WHERE code = 'other')"
    await db.execute(text(off), {"on": False})
    await db.commit()
    try:
        body = await create(client, db, "other", WEST)
        assert body["service"] is None and body["priority"] == "medium"
    finally:
        await db.execute(text(off), {"on": True})
        await db.commit()
