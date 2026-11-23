"""Стрічка сповіщень: GET /notifications, позначка «прочитано» (KAN-61, табл. 18)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification
from app.modules.users.models import User
from tests.factories import auth, make_driver, make_staff
from tests.test_reports_status import WEST, new_report, patch

URL = "/api/v1/notifications"


async def seed(db: AsyncSession, user: User, count: int) -> list[int]:
    items = [
        Notification(user_id=user.id, type="STATUS_CHANGED", message=f"Сповіщення {i}")
        for i in range(1, count + 1)
    ]
    db.add_all(items)
    await db.commit()
    return [n.id for n in items]


async def test_feed_after_status_change(client: AsyncClient, db: AsyncSession) -> None:
    """Наскрізно: диспетчер змінив статус - водій бачить сповіщення у стрічці."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, report["id"], status="accepted")

    response = await client.get(URL, headers=auth(report["author"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1 and body["unread"] == 1
    item = body["items"][0]
    assert item["request_id"] == report["id"]
    assert "«Прийнята»" in item["message"] and item["is_read"] is False


async def test_newest_first_and_pagination(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    await seed(db, driver, 5)
    first = (await client.get(URL, params={"limit": 2}, headers=auth(driver))).json()
    last = (await client.get(URL, params={"limit": 2, "offset": 4}, headers=auth(driver))).json()
    assert [i["message"] for i in first["items"]] == ["Сповіщення 5", "Сповіщення 4"]
    assert [i["message"] for i in last["items"]] == ["Сповіщення 1"]
    assert first["total"] == last["total"] == 5


async def test_mark_read(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    first, second = await seed(db, driver, 2)

    response = await client.post(f"{URL}/{first}/read", headers=auth(driver))
    assert response.status_code == 200 and response.json()["is_read"] is True

    body = (await client.get(URL, params={"unread_only": True}, headers=auth(driver))).json()
    assert body["unread"] == 1 and [i["id"] for i in body["items"]] == [second]


async def test_mark_all_read(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    await seed(db, driver, 3)
    response = await client.post(f"{URL}/read-all", headers=auth(driver))
    assert response.json() == {"updated": 3}
    assert (await client.get(URL, headers=auth(driver))).json()["unread"] == 0


async def test_only_own_notifications(client: AsyncClient, db: AsyncSession) -> None:
    """Чужі сповіщення не видно й не можна позначити (404, а не 403 - щоб не розкривати їх)."""
    owner = await make_driver(db)
    stranger = await make_driver(db, email="stranger@test.ua")
    [note_id] = await seed(db, owner, 1)

    assert (await client.get(URL, headers=auth(stranger))).json()["total"] == 0
    assert (await client.post(f"{URL}/{note_id}/read", headers=auth(stranger))).status_code == 404
    await client.post(f"{URL}/read-all", headers=auth(stranger))
    assert (await client.get(URL, headers=auth(owner))).json()["unread"] == 1


async def test_staff_have_feed_too(client: AsyncClient, db: AsyncSession) -> None:
    """Стрічка доступна всім, хто увійшов (табл. 18: «Автентифіковані»)."""
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    response = await client.get(URL, headers=auth(dispatcher))
    assert response.status_code == 200 and response.json()["total"] == 0


async def test_anonymous_401(client: AsyncClient) -> None:
    assert (await client.get(URL)).status_code == 401
    assert (await client.post(f"{URL}/read-all")).status_code == 401