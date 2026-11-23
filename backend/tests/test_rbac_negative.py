"""QA: негативні сценарії доступу RBAC (KAN-74, табл. 14, підрозд. 3.4).

Кожна відмова має повернути 403 без даних заявки, не змінити запис і залишити в
AuditLog рівно одну подію ACCESS_DENIED з роллю, ендпоінтом, причиною й correlation_id
запиту. Перевіряються справжні ендпоінти: PATCH /reports/{id}/status,
GET /reports/{id}/history, /work-orders і GET /audit.

Сценарії, які вже покриті іншими тестами, тут не дублюються:
диспетчер іншого району (test_reports_status, test_reports_history), чужий водій
(test_reports_history), «Усунена» від підрядника (test_reports_status), прогрес від
інших ролей (test_work_orders).
"""

from datetime import date, timedelta
from itertools import count

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RequestStatus
from app.modules.audit.models import AuditLog
from app.modules.reports.models import Request
from app.modules.users.models import User
from tests.factories import auth, make_contractor, make_driver, make_staff

URL = "/api/v1/reports"
WEST_POINT = {"latitude": 49.84, "longitude": 23.98}
WEST = "Комунальна служба Залізничного району (демо)"
POLICE = "Дорожня поліція (демо)"
FORBIDDEN = {"detail": "Недостатньо прав для цієї дії"}
_emails = count(1)


# ---------- підготовка ----------


async def new_report(client: AsyncClient, db: AsyncSession, problem_type: str = "pothole") -> dict:
    driver = await make_driver(db, email=f"author{next(_emails)}@test.ua")
    response = await client.post(
        URL,
        data={"problem_type": problem_type, "comment": "Яма біля зупинки", **WEST_POINT},
        headers=auth(driver),
    )
    assert response.status_code == 201, response.text
    return {**response.json(), "author": driver}


async def assigned_work(
    client: AsyncClient, db: AsyncSession, contractor: User, dispatcher: User, admin: User
) -> dict:
    """Заявка комунальної служби, прийнята й призначена підряднику."""
    report = await new_report(client, db)
    response = await client.patch(
        f"{URL}/{report['id']}/status", json={"status": "accepted"}, headers=auth(dispatcher)
    )
    assert response.status_code == 200, response.text
    response = await client.post(
        "/api/v1/work-orders",
        json={
            "request_id": report["id"],
            "contractor_id": contractor.contractor_id,
            "deadline": (date.today() + timedelta(days=14)).isoformat(),
        },
        headers=auth(admin),
    )
    assert response.status_code in (200, 201), response.text
    return report


async def denials(db: AsyncSession) -> list[AuditLog]:
    rows = await db.scalars(
        select(AuditLog).where(AuditLog.action == "ACCESS_DENIED").order_by(AuditLog.id)
    )
    return list(rows)


async def assert_denied(
    db: AsyncSession,
    response: Response,
    user: User,
    *,
    role: str,
    reason: str,
    endpoint: str,
    entity_id: int | None = None,
) -> None:
    """403 без даних і рівно один ACCESS_DENIED з повним контекстом відмови."""
    assert response.status_code == 403, response.text
    assert response.json() == FORBIDDEN
    [entry] = await denials(db)
    assert entry.actor_id == user.id
    assert entry.actor_role == role
    assert entry.result == "denied"
    assert entry.new_value["reason"] == reason
    assert entry.new_value["endpoint"] == endpoint
    if entity_id is not None:
        assert entry.entity_id == entity_id
    assert str(entry.correlation_id) == response.headers["X-Request-ID"]


async def status_of(db: AsyncSession, report_id: int) -> RequestStatus:
    return await db.scalar(
        select(Request.status)
        .where(Request.id == report_id)
        .execution_options(populate_existing=True)
    )


# ---------- сценарії з KAN-74 ----------


async def test_tc01_driver_cannot_change_status(client: AsyncClient, db: AsyncSession) -> None:
    """Водій намагається змінити статус власної заявки."""
    report = await new_report(client, db)
    driver = report["author"]
    response = await client.patch(
        f"{URL}/{report['id']}/status", json={"status": "accepted"}, headers=auth(driver)
    )
    await assert_denied(
        db,
        response,
        driver,
        role="driver",
        reason="no_policy",
        endpoint=f"PATCH {URL}/{report['id']}/status",
    )
    assert await status_of(db, report["id"]) == RequestStatus.NEW


async def test_tc02_police_cannot_open_communal_report(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Поліція відкриває заявку комунальної служби (яма без копії поліції)."""
    report = await new_report(client, db)
    police = await make_staff(db, "dispatcher", service_name=POLICE)
    response = await client.get(f"{URL}/{report['id']}/history", headers=auth(police))
    await assert_denied(
        db,
        response,
        police,
        role="police",
        reason="out_of_scope:service",
        endpoint=f"GET {URL}/{report['id']}/history",
        entity_id=report["id"],
    )
    assert "Яма" not in response.text


async def test_tc03_police_cannot_change_communal_status(
    client: AsyncClient, db: AsyncSession
) -> None:
    report = await new_report(client, db)
    police = await make_staff(db, "dispatcher", service_name=POLICE)
    response = await client.patch(
        f"{URL}/{report['id']}/status", json={"status": "accepted"}, headers=auth(police)
    )
    await assert_denied(
        db,
        response,
        police,
        role="police",
        reason="out_of_scope:service",
        endpoint=f"PATCH {URL}/{report['id']}/status",
        entity_id=report["id"],
    )
    assert await status_of(db, report["id"]) == RequestStatus.NEW


async def test_tc04_contractor_does_not_see_foreign_work(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Підрядник бачить у списку лише свої роботи, а чужу відкрити не може."""
    mine = await make_contractor(db, "Свій підрядник")
    other = await make_contractor(db, "Чужий підрядник")
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    admin = await make_staff(db, "admin")
    own_work = await assigned_work(client, db, mine, dispatcher, admin)
    foreign_work = await assigned_work(client, db, other, dispatcher, admin)

    listed = await client.get("/api/v1/work-orders", headers=auth(mine))
    assert listed.status_code == 200, listed.text
    ids = {w.get("request_id", w.get("id")) for w in listed.json()}
    assert own_work["id"] in ids and foreign_work["id"] not in ids

    response = await client.get(f"{URL}/{foreign_work['id']}/history", headers=auth(mine))
    await assert_denied(
        db,
        response,
        mine,
        role="contractor",
        reason="out_of_scope:own",
        endpoint=f"GET {URL}/{foreign_work['id']}/history",
        entity_id=foreign_work["id"],
    )


async def test_tc05_contractor_cannot_update_foreign_progress(
    client: AsyncClient, db: AsyncSession
) -> None:
    mine = await make_contractor(db, "Свій підрядник")
    other = await make_contractor(db, "Чужий підрядник")
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    admin = await make_staff(db, "admin")
    foreign_work = await assigned_work(client, db, other, dispatcher, admin)

    endpoint = f"/api/v1/work-orders/{foreign_work['id']}/progress"
    response = await client.post(endpoint, data={"progress_percent": 50}, headers=auth(mine))
    await assert_denied(
        db,
        response,
        mine,
        role="contractor",
        reason="out_of_scope:own",
        endpoint=f"POST {endpoint}",
        entity_id=foreign_work["id"],
    )


@pytest.mark.parametrize(
    ("key", "role"),
    [
        ("driver", "driver"),
        ("dispatcher", "dispatcher"),
        ("police", "police"),
        ("contractor", "contractor"),
    ],
)
async def test_tc06_audit_without_rights(
    client: AsyncClient, db: AsyncSession, key: str, role: str
) -> None:
    """Перегляд журналу аудиту без прав: відмова пишеться, AUDIT_VIEWED - ні."""
    user = {
        "driver": lambda: make_driver(db),
        "dispatcher": lambda: make_staff(db, "dispatcher", service_name=WEST),
        "police": lambda: make_staff(db, "dispatcher", service_name=POLICE),
        "contractor": lambda: make_contractor(db),
    }[key]
    user = await user()
    response = await client.get("/api/v1/audit", headers=auth(user))
    await assert_denied(
        db, response, user, role=role, reason="no_policy", endpoint="GET /api/v1/audit"
    )
    viewed = await db.scalar(select(AuditLog).where(AuditLog.action == "AUDIT_VIEWED"))
    assert viewed is None


async def test_tc07_audit_actions_without_rights(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    response = await client.get("/api/v1/audit/actions", headers=auth(driver))
    await assert_denied(
        db,
        response,
        driver,
        role="driver",
        reason="no_policy",
        endpoint="GET /api/v1/audit/actions",
    )


# ---------- додаткові сценарії матриці (табл. 14) ----------


async def test_tc08_admin_cannot_change_status(client: AsyncClient, db: AsyncSession) -> None:
    """Розділення обов'язків: адміністратор не змінює статуси заявок."""
    report = await new_report(client, db)
    admin = await make_staff(db, "admin")
    response = await client.patch(
        f"{URL}/{report['id']}/status",
        json={"status": "rejected", "reject_reason": "тест"},
        headers=auth(admin),
    )
    await assert_denied(
        db,
        response,
        admin,
        role="admin",
        reason="no_policy",
        endpoint=f"PATCH {URL}/{report['id']}/status",
    )
    assert await status_of(db, report["id"]) == RequestStatus.NEW


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("patch", "/status", {"status": "accepted"}),
        ("get", "/history", None),
    ],
)
async def test_tc09_data_governance_does_not_work_with_reports(
    client: AsyncClient, db: AsyncSession, method: str, path: str, body: dict | None
) -> None:
    report = await new_report(client, db)
    dg = await make_staff(db, "data_governance")
    url = f"{URL}/{report['id']}{path}"
    kwargs = {"json": body} if body else {}
    response = await getattr(client, method)(url, headers=auth(dg), **kwargs)
    await assert_denied(
        db,
        response,
        dg,
        role="data_governance",
        reason="no_policy",
        endpoint=f"{method.upper()} {url}",
    )


async def test_tc10_driver_cannot_assign_contractor(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    contractor = await make_contractor(db)
    driver = report["author"]
    response = await client.post(
        "/api/v1/work-orders",
        json={
            "request_id": report["id"],
            "contractor_id": contractor.contractor_id,
            "deadline": (date.today() + timedelta(days=7)).isoformat(),
        },
        headers=auth(driver),
    )
    await assert_denied(
        db, response, driver, role="driver", reason="no_policy", endpoint="POST /api/v1/work-orders"
    )


async def test_tc11_anonymous_gets_401_without_data(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    for response in (
        await client.get(f"{URL}/{report['id']}/history"),
        await client.patch(f"{URL}/{report['id']}/status", json={"status": "accepted"}),
        await client.get("/api/v1/audit"),
    ):
        assert response.status_code == 401
        assert "Яма" not in response.text
    assert await status_of(db, report["id"]) == RequestStatus.NEW


async def test_tc12_forged_token_rejected(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.e30.forged"}
    response = await client.get(f"{URL}/{report['id']}/history", headers=headers)
    assert response.status_code == 401


# ---------- контрольні позитивні сценарії ----------


async def test_police_sees_accident_and_contractor_own_work(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Доступ у межах ролі працює, і ACCESS_DENIED не пишеться."""
    accident = await new_report(client, db, "accident")
    police = await make_staff(db, "dispatcher", service_name=POLICE)
    assert (
        await client.get(f"{URL}/{accident['id']}/history", headers=auth(police))
    ).status_code == 200

    mine = await make_contractor(db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    admin = await make_staff(db, "admin")
    work = await assigned_work(client, db, mine, dispatcher, admin)
    assert (await client.get(f"{URL}/{work['id']}/history", headers=auth(mine))).status_code == 200
    assert await denials(db) == []
