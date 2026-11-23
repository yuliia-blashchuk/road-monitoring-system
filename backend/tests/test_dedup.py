"""Дедуплікація і «Теж бачу» (KAN-63, F-21, F-22, БП-1, DQ-07).

Заявки створюються напряму в БД: API створення заявки - окрема задача (KAN-57).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Priority, RequestStatus
from app.modules.admin.models import ProblemType, Service
from app.modules.audit.models import AuditLog
from app.modules.dedup import service as dedup
from app.modules.reports.models import Confirmation, Request
from app.modules.users.models import User
from tests.test_rbac import auth, make_user

URL_NEARBY = "/api/v1/reports/nearby"

# Центр Львова; 0.00018° широти ≈ 20 м, 0.00036° ≈ 40 м.
LAT, LNG = 49.8397, 24.0297
M20, M40 = 0.00018, 0.00036


async def type_id(db: AsyncSession, code: str) -> int:
    return await db.scalar(select(ProblemType.id).where(ProblemType.code == code))


async def make_request(
    db: AsyncSession,
    *,
    author: User | None = None,
    code: str = "pothole",
    lat: float = LAT,
    lng: float = LNG,
    status: RequestStatus = RequestStatus.NEW,
    priority: Priority = Priority.MEDIUM,
    confirmations: int = 0,
) -> Request:
    service_id = await db.scalar(select(Service.id).limit(1))
    request = Request(
        author_id=author.id if author else None,
        problem_type_id=await type_id(db, code),
        service_id=service_id,
        location=f"SRID=4326;POINT({lng} {lat})",
        status=status,
        priority=priority,
        confirmations_count=confirmations,
        reject_reason="тест" if status == RequestStatus.REJECTED else None,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return request


async def make_drivers(db: AsyncSession, count: int) -> list[User]:
    """Кілька водіїв з різними email (make_user з test_rbac створює одного «driver»)."""
    drivers = []
    for i in range(count):
        user = await make_user(db, "driver")
        user.email = f"driver{i}@test.ua"
        await db.commit()
        drivers.append(user)
    return drivers


def confirm_url(request_id: int) -> str:
    return f"/api/v1/reports/{request_id}/confirm"


# ---------- пошук дублікатів ----------


async def test_finds_same_type_within_30m(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_user(db, "driver")
    near = await make_request(db, lat=LAT + M20)
    await make_request(db, lat=LAT + M40)  # 40 м - вже не дублікат
    await make_request(db, code="obstacle")  # інший тип
    await make_request(db, status=RequestStatus.RESOLVED)  # закрита
    await make_request(db, status=RequestStatus.REJECTED)  # закрита

    response = await client.get(
        URL_NEARBY,
        params={"lat": LAT, "lng": LNG, "problem_type_id": await type_id(db, "pothole")},
        headers=auth(driver),
    )
    assert response.status_code == 200, response.text
    items = response.json()
    assert [i["id"] for i in items] == [near.id]
    assert 15 < items[0]["distance_m"] < 25
    assert items[0]["lat"] == pytest.approx(LAT + M20)
    assert items[0]["lng"] == pytest.approx(LNG)


async def test_nearby_sorted_by_distance_and_public_fields_only(
    client: AsyncClient, db: AsyncSession
) -> None:
    author = await make_user(db, "driver")
    far = await make_request(db, author=author, lat=LAT + M20)
    close = await make_request(db, author=author, lat=LAT + 0.00005)

    response = await client.get(
        URL_NEARBY,
        params={"lat": LAT, "lng": LNG, "problem_type_id": await type_id(db, "pothole")},
        headers=auth(author),
    )
    items = response.json()
    assert [i["id"] for i in items] == [close.id, far.id]
    # Схожу заявку бачить інший водій - без автора, коментаря і пріоритету (табл. 13).
    assert not {"author_id", "comment", "priority"} & items[0].keys()


async def test_find_duplicates_for_reports_module(db: AsyncSession) -> None:
    """Функція, яку викличе створення заявки (KAN-57)."""
    existing = await make_request(db, lat=LAT + M20)
    rows = await dedup.find_duplicates(
        db, lat=LAT, lng=LNG, problem_type_id=await type_id(db, "pothole")
    )
    assert [r.request.id for r in rows] == [existing.id]
    assert (
        await dedup.find_duplicates(
            db, lat=LAT, lng=LNG, problem_type_id=await type_id(db, "accident")
        )
        == []
    )


async def test_nearby_validates_coordinates(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_user(db, "driver")
    response = await client.get(
        URL_NEARBY, params={"lat": 120, "lng": LNG, "problem_type_id": 1}, headers=auth(driver)
    )
    assert response.status_code == 422


@pytest.mark.parametrize("key", ["dispatcher", "police", "contractor", "admin"])
async def test_nearby_only_for_driver(client: AsyncClient, db: AsyncSession, key: str) -> None:
    user = await make_user(db, key)
    response = await client.get(
        URL_NEARBY, params={"lat": LAT, "lng": LNG, "problem_type_id": 1}, headers=auth(user)
    )
    assert response.status_code == 403


async def test_nearby_requires_login(client: AsyncClient) -> None:
    response = await client.get(URL_NEARBY, params={"lat": LAT, "lng": LNG, "problem_type_id": 1})
    assert response.status_code == 401


# ---------- «Теж бачу» ----------


async def test_confirm_increments_counter(client: AsyncClient, db: AsyncSession) -> None:
    author, other = await make_drivers(db, 2)
    request = await make_request(db, author=author)

    response = await client.post(confirm_url(request.id), headers=auth(other))
    assert response.status_code == 200, response.text
    assert response.json() == {
        "request_id": request.id,
        "confirmations_count": 1,
        "priority_raised": False,
    }

    await db.refresh(request)
    assert request.confirmations_count == 1
    saved = await db.scalar(select(Confirmation).where(Confirmation.request_id == request.id))
    assert saved.user_id == other.id and saved.still_exists is True

    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "REPORT_CONFIRMED"))
    assert entry.actor_id == other.id
    assert entry.entity_id == request.id
    assert entry.old_value == {"confirmations_count": 0}
    assert entry.new_value == {"confirmations_count": 1}


async def test_confirm_twice_counts_once(client: AsyncClient, db: AsyncSession) -> None:
    author, other = await make_drivers(db, 2)
    request = await make_request(db, author=author)

    assert (await client.post(confirm_url(request.id), headers=auth(other))).status_code == 200
    second = await client.post(confirm_url(request.id), headers=auth(other))
    assert second.status_code == 409
    assert second.json()["detail"] == "Ви вже підтвердили цю заявку"

    await db.refresh(request)
    assert request.confirmations_count == 1


async def test_cannot_confirm_own_report(client: AsyncClient, db: AsyncSession) -> None:
    author = await make_user(db, "driver")
    request = await make_request(db, author=author)
    response = await client.post(confirm_url(request.id), headers=auth(author))
    assert response.status_code == 409
    assert response.json()["detail"] == "Не можна підтвердити власну заявку"


@pytest.mark.parametrize("closed", [RequestStatus.RESOLVED, RequestStatus.REJECTED])
async def test_cannot_confirm_closed_report(
    client: AsyncClient, db: AsyncSession, closed: RequestStatus
) -> None:
    driver = await make_user(db, "driver")
    request = await make_request(db, status=closed)
    response = await client.post(confirm_url(request.id), headers=auth(driver))
    assert response.status_code == 409


async def test_confirm_unknown_report(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_user(db, "driver")
    assert (await client.post(confirm_url(999999), headers=auth(driver))).status_code == 404


@pytest.mark.parametrize("key", ["dispatcher", "police", "contractor", "admin"])
async def test_confirm_only_for_driver(client: AsyncClient, db: AsyncSession, key: str) -> None:
    user = await make_user(db, key)
    request = await make_request(db)
    assert (await client.post(confirm_url(request.id), headers=auth(user))).status_code == 403


# ---------- БП-1: 5 підтверджень піднімають пріоритет ----------


async def test_fifth_confirmation_raises_priority_once(
    client: AsyncClient, db: AsyncSession
) -> None:
    drivers = await make_drivers(db, 6)
    request = await make_request(db, priority=Priority.MEDIUM)

    raised = []
    for driver in drivers:
        response = await client.post(confirm_url(request.id), headers=auth(driver))
        assert response.status_code == 200, response.text
        raised.append(response.json()["priority_raised"])

    assert raised == [False, False, False, False, True, False]
    await db.refresh(request)
    assert request.confirmations_count == 6
    assert request.priority == Priority.HIGH  # лише на один рівень

    recalculated = await db.scalars(
        select(AuditLog).where(AuditLog.action == "PRIORITY_RECALCULATED")
    )
    entries = list(recalculated)
    assert len(entries) == 1
    assert entries[0].actor_id is None  # дія системи
    assert entries[0].old_value == {"priority": "medium"}
    assert entries[0].new_value["priority"] == "high"


async def test_critical_priority_stays_critical(client: AsyncClient, db: AsyncSession) -> None:
    (driver,) = await make_drivers(db, 1)
    request = await make_request(db, priority=Priority.CRITICAL, confirmations=4)
    response = await client.post(confirm_url(request.id), headers=auth(driver))
    assert response.json()["priority_raised"] is False
    await db.refresh(request)
    assert request.priority == Priority.CRITICAL


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (Priority.LOW, Priority.MEDIUM),
        (Priority.MEDIUM, Priority.HIGH),
        (Priority.HIGH, Priority.CRITICAL),
        (Priority.CRITICAL, Priority.CRITICAL),
    ],
)
def test_raise_priority(before: Priority, after: Priority) -> None:
    assert dedup.raise_priority(before) == after


async def test_confirmations_table_count_matches_counter(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Лічильник у заявці дорівнює кількості записів Confirmation (DQ-07)."""
    drivers = await make_drivers(db, 3)
    request = await make_request(db)
    for driver in drivers:
        await client.post(confirm_url(request.id), headers=auth(driver))
    rows = await db.scalar(
        select(func.count()).select_from(Confirmation).where(Confirmation.request_id == request.id)
    )
    await db.refresh(request)
    assert rows == request.confirmations_count == 3
