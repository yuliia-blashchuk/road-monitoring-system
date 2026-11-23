"""Читання заявок: карта, «Мої звернення», картка, фото (табл. 18; табл. 11 - поля за роллю)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from app.modules.reports.models import Request
from tests.factories import auth, make_contractor, make_driver, make_staff
from tests.test_reports_photos import image_bytes
from tests.test_reports_status import EAST, EAST_POINT, WEST, WEST_POINT, new_report, patch

URL = "/api/v1/reports"


async def report_with_photo(client: AsyncClient, db: AsyncSession) -> dict:
    driver = await make_driver(db, email="photo-author@test.ua")
    response = await client.post(
        URL,
        data={"problem_type": "pothole", "comment": "Глибока яма", **WEST_POINT},
        files=[("photos", ("a.jpg", image_bytes(), "image/jpeg"))],
        headers=auth(driver),
    )
    assert response.status_code == 201, response.text
    return {**response.json(), "author": driver}


# ---------- публічна карта ----------


async def test_map_is_public_and_has_only_public_fields(
    client: AsyncClient, db: AsyncSession
) -> None:
    report = await report_with_photo(client, db)
    response = await client.get(URL)  # без токена
    assert response.status_code == 200, response.text
    [item] = response.json()
    assert item["id"] == report["id"] and item["number"] == report["number"]
    assert item["problem_type"] == "pothole" and item["problem_label"]
    assert item["status"] == "new" and item["status_label"] == "Нова"
    assert item["lat"] == pytest.approx(WEST_POINT["latitude"])
    assert item["lng"] == pytest.approx(WEST_POINT["longitude"])
    assert item["color"].startswith("#") and item["icon"]
    for hidden in ("comment", "author", "author_id", "priority", "photos"):
        assert hidden not in item


async def test_map_hides_closed_and_suspicious(client: AsyncClient, db: AsyncSession) -> None:
    """БП-4: усунені й відхилені прибираються з карти; підозрілі теж не показуються."""
    rejected = await new_report(client, db)
    suspicious = await new_report(client, db)
    visible = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, rejected["id"], status="rejected", reject_reason="Дубль")
    await db.execute(
        update(Request).where(Request.id == suspicious["id"]).values(is_suspicious=True)
    )
    await db.commit()

    ids = [item["id"] for item in (await client.get(URL)).json()]
    assert ids == [visible["id"]]


async def test_map_filters(client: AsyncClient, db: AsyncSession) -> None:
    west = await new_report(client, db, "pothole", WEST_POINT)
    east = await new_report(client, db, "accident", EAST_POINT)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, west["id"], status="accepted")

    async def ids(**params) -> list[int]:
        response = await client.get(URL, params=params)
        assert response.status_code == 200, response.text
        return sorted(item["id"] for item in response.json())

    assert await ids(type="accident") == [east["id"]]
    assert await ids(type=["accident", "pothole"]) == sorted([west["id"], east["id"]])
    assert await ids(status="accepted") == [west["id"]]
    assert await ids(bbox="23.92,49.80,24.03,49.88") == [west["id"]]  # лише захід
    assert await ids(bbox="24.03,49.80,24.14,49.88") == [east["id"]]  # лише схід


@pytest.mark.parametrize(
    "params",
    [
        {"bbox": "1,2,3"},
        {"bbox": "a,b,c,d"},
        {"bbox": "24.1,49.8,24.0,49.9"},
        {"status": "resolved"},
    ],
)
async def test_map_bad_params(client: AsyncClient, params: dict) -> None:
    assert (await client.get(URL, params=params)).status_code == 422


# ---------- «Мої звернення» ----------


async def test_my_reports_only_own(client: AsyncClient, db: AsyncSession) -> None:
    mine = await report_with_photo(client, db)
    await new_report(client, db)  # чужа
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, mine["id"], status="rejected", reject_reason="Дубль")

    response = await client.get(f"{URL}/my", headers=auth(mine["author"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    [item] = body["items"]
    assert item["id"] == mine["id"]
    assert item["status"] == "rejected"  # закриті теж видно у власному списку
    assert item["comment"] == "Глибока яма"
    assert item["service"] == WEST and item["photos_count"] == 1


async def test_my_reports_pagination(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db, email="many@test.ua")
    for _ in range(3):
        response = await client.post(
            URL, data={"problem_type": "pothole", **WEST_POINT}, headers=auth(driver)
        )
        assert response.status_code == 201
    page = (await client.get(f"{URL}/my", params={"limit": 2}, headers=auth(driver))).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    numbers = [item["number"] for item in page["items"]]
    assert numbers == sorted(numbers, reverse=True)  # новіші спершу


@pytest.mark.parametrize("role", ["dispatcher", "admin"])
async def test_my_reports_only_for_drivers(
    client: AsyncClient, db: AsyncSession, role: str
) -> None:
    user = await make_staff(db, role, service_name=WEST if role == "dispatcher" else None)
    assert (await client.get(f"{URL}/my", headers=auth(user))).status_code == 403


# ---------- картка ----------


async def test_card_for_author(client: AsyncClient, db: AsyncSession) -> None:
    """Водій бачить свою заявку з коментарем і фото, але без внутрішніх полів служби."""
    report = await report_with_photo(client, db)
    response = await client.get(f"{URL}/{report['id']}", headers=auth(report["author"]))
    assert response.status_code == 200, response.text
    card = response.json()
    assert card["comment"] == "Глибока яма" and card["service"] == WEST
    assert len(card["photos"]) == 1 and card["photos"][0]["kind"] == "before"
    assert card["next_statuses"] == []  # водій статуси не змінює
    for hidden in ("priority", "deadline", "author", "author_id", "is_suspicious"):
        assert hidden not in card


async def test_card_for_dispatcher(client: AsyncClient, db: AsyncSession) -> None:
    """Служба бачить внутрішні поля й автора лише під псевдонімом."""
    report = await report_with_photo(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    card = (await client.get(f"{URL}/{report['id']}", headers=auth(dispatcher))).json()
    assert card["priority"] == "medium"
    assert card["author"].startswith("Заявник #") and "author_id" not in card
    assert card["comment"] == "Глибока яма"
    assert set(card["next_statuses"]) == {"accepted", "rejected"}


async def test_card_for_contractor_without_personal_data(
    client: AsyncClient, db: AsyncSession
) -> None:
    """БП-5: підрядник бачить призначену заявку без автора й коментаря."""
    report = await report_with_photo(client, db)
    contractor = await make_contractor(db)
    await db.execute(
        update(Request)
        .where(Request.id == report["id"])
        .values(contractor_id=contractor.contractor_id)
    )
    await db.commit()
    card = (await client.get(f"{URL}/{report['id']}", headers=auth(contractor))).json()
    assert "comment" not in card and "author" not in card and "author_id" not in card
    assert card["photos"] == []  # оригінали фото водія - не для підрядника


async def test_card_for_admin(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    admin = await make_staff(db, "admin")
    card = (await client.get(f"{URL}/{report['id']}", headers=auth(admin))).json()
    assert card["author_id"] == report["author"].id


async def test_card_access_denied(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    stranger = await make_driver(db, email="stranger@test.ua")
    other_district = await make_staff(db, "dispatcher", service_name=EAST)
    for user in (stranger, other_district):
        assert (await client.get(f"{URL}/{report['id']}", headers=auth(user))).status_code == 403
    assert (await client.get(f"{URL}/{report['id']}")).status_code == 401
    admin = await make_staff(db, "admin")
    assert (await client.get(f"{URL}/999999", headers=auth(admin))).status_code == 404


# ---------- фото ----------


async def test_photo_file(client: AsyncClient, db: AsyncSession) -> None:
    report = await report_with_photo(client, db)
    card = (await client.get(f"{URL}/{report['id']}", headers=auth(report["author"]))).json()
    url = card["photos"][0]["url"]

    response = await client.get(url, headers=auth(report["author"]))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"  # початок JPEG


async def test_photo_access(client: AsyncClient, db: AsyncSession) -> None:
    report = await report_with_photo(client, db)
    card = (await client.get(f"{URL}/{report['id']}", headers=auth(report["author"]))).json()
    url = card["photos"][0]["url"]

    stranger = await make_driver(db, email="stranger@test.ua")
    assert (await client.get(url, headers=auth(stranger))).status_code == 403
    assert (await client.get(url)).status_code == 401
    missing = f"{URL}/{report['id']}/photos/999999"
    assert (await client.get(missing, headers=auth(report["author"]))).status_code == 404


async def test_admin_photo_view_is_audited(client: AsyncClient, db: AsyncSession) -> None:
    """Перегляд оригіналу фото адміністратором журналюється (табл. 14, log_access)."""
    report = await report_with_photo(client, db)
    admin = await make_staff(db, "admin")
    card = (await client.get(f"{URL}/{report['id']}", headers=auth(admin))).json()
    assert (await client.get(card["photos"][0]["url"], headers=auth(admin))).status_code == 200

    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "PHOTO_VIEWED"))
    assert entry.actor_id == admin.id and entry.entity_id == report["id"]