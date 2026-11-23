"""Черга заявок служби: GET /queue (UC-02, табл. 18)."""

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.models import Request
from tests.factories import auth, make_contractor, make_driver, make_staff
from tests.test_reports_status import EAST, EAST_POINT, POLICE, WEST, new_report, patch

URL = "/api/v1/queue"


async def numbers(client: AsyncClient, user, **params) -> list[int]:
    response = await client.get(URL, params=params, headers=auth(user))
    assert response.status_code == 200, response.text
    return [item["number"] for item in response.json()["items"]]


async def test_queue_sorted_by_priority_then_time(client: AsyncClient, db: AsyncSession) -> None:
    """Спершу найтерміновіші, усередині пріоритету - старіші раніше."""
    low = await new_report(client, db, "damaged_surface")  # low
    medium_old = await new_report(client, db, "pothole")  # medium
    medium_new = await new_report(client, db, "pothole")  # medium
    high = await new_report(client, db, "traffic_light")  # high
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)

    assert await numbers(client, dispatcher) == [
        high["number"],
        medium_old["number"],
        medium_new["number"],
        low["number"],
    ]


async def test_queue_item_fields(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    body = (await client.get(URL, headers=auth(dispatcher))).json()
    assert body["total"] == 1
    [item] = body["items"]
    assert item["priority"] == "medium" and item["service"] == WEST
    assert item["author"].startswith("Заявник #")
    assert item["is_copy"] is False
    assert set(item["next_statuses"]) == {"accepted", "rejected"}
    assert item["id"] == report["id"]


async def test_queue_only_own_service_and_copies(client: AsyncClient, db: AsyncSession) -> None:
    """Захід бачить свої заявки й копію перешкоди; схід - лише свої."""
    west = await new_report(client, db, "pothole")
    obstacle = await new_report(client, db, "obstacle")  # поліція + копія західній службі
    east = await new_report(client, db, "pothole", EAST_POINT)
    west_dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    east_dispatcher = await make_staff(db, "dispatcher", service_name=EAST)
    police = await make_staff(db, "dispatcher", service_name=POLICE)

    body = (await client.get(URL, headers=auth(west_dispatcher))).json()
    copies = {item["number"]: item["is_copy"] for item in body["items"]}
    assert copies == {west["number"]: False, obstacle["number"]: True}
    assert await numbers(client, east_dispatcher) == [east["number"]]
    assert await numbers(client, police) == [obstacle["number"]]


async def test_queue_hides_closed_by_default(client: AsyncClient, db: AsyncSession) -> None:
    open_report = await new_report(client, db)
    closed = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, closed["id"], status="rejected", reject_reason="Дубль")

    assert await numbers(client, dispatcher) == [open_report["number"]]
    assert await numbers(client, dispatcher, status="rejected") == [closed["number"]]


async def test_admin_sees_all(client: AsyncClient, db: AsyncSession) -> None:
    await new_report(client, db)
    await new_report(client, db, "pothole", EAST_POINT)
    admin = await make_staff(db, "admin")
    assert len(await numbers(client, admin)) == 2


async def test_contractor_sees_assigned_without_personal_data(
    client: AsyncClient, db: AsyncSession
) -> None:
    assigned = await new_report(client, db)
    await new_report(client, db)  # не призначена
    contractor = await make_contractor(db)
    await db.execute(
        update(Request)
        .where(Request.id == assigned["id"])
        .values(contractor_id=contractor.contractor_id)
    )
    await db.commit()

    body = (await client.get(URL, headers=auth(contractor))).json()
    [item] = body["items"]
    assert item["number"] == assigned["number"]
    assert item["author"] is None and item["comment"] is None  # БП-5


async def test_driver_has_no_queue(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    assert (await client.get(URL, headers=auth(driver))).status_code == 403
    assert (await client.get(URL)).status_code == 401


async def test_queue_pagination(client: AsyncClient, db: AsyncSession) -> None:
    for _ in range(3):
        await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    body = (await client.get(URL, params={"limit": 2}, headers=auth(dispatcher))).json()
    assert body["total"] == 3 and len(body["items"]) == 2