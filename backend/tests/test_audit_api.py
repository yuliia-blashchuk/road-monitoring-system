"""Перегляд журналу аудиту: GET /audit з фільтрами й пагінацією (KAN-60, QR-13, п. 3.8)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit import service as audit
from app.modules.audit.models import AuditLog
from tests.factories import auth, make_driver, make_staff

URL = "/api/v1/audit"


async def seed(db: AsyncSession) -> None:
    """Кілька записів різних дій, ролей і сутностей."""
    audit.record(db, "LOGIN_SUCCESS", actor_id=None, actor_role="driver")
    audit.record(db, "LOGIN_FAILED", result="failure", new_value={"email": "d***@test.ua"})
    for request_id in (1, 2):
        audit.record(
            db,
            "STATUS_CHANGED",
            actor_role="dispatcher",
            entity_type="request",
            entity_id=request_id,
            old_value={"status": "new"},
            new_value={"status": "accepted"},
        )
    audit.record(db, "ACCESS_DENIED", actor_role="driver", entity_type="audit", result="denied")
    await db.commit()


async def get(client: AsyncClient, user, **params):
    response = await client.get(URL, params=params, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


async def test_page_shape_and_order(client: AsyncClient, db: AsyncSession) -> None:
    await seed(db)
    admin = await make_staff(db, "admin")
    body = await get(client, admin)
    assert body["total"] == 5 and body["limit"] == 100 and body["offset"] == 0
    ids = [item["id"] for item in body["items"]]
    assert ids == sorted(ids, reverse=True)  # новіші спершу
    assert {"ip", "correlation_id", "old_value", "new_value"} <= set(body["items"][0])


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"action": "STATUS_CHANGED"}, 2),
        ({"action": "status_changed"}, 2),  # регістр не важливий
        ({"result": "failure"}, 1),
        ({"result": "denied"}, 1),
        ({"actor_role": "driver"}, 2),
        ({"entity_type": "request"}, 2),
        ({"entity_type": "request", "entity_id": 2}, 1),
        ({"action": "STATUS_CHANGED", "actor_role": "driver"}, 0),
    ],
)
async def test_filters(client: AsyncClient, db: AsyncSession, params: dict, expected: int) -> None:
    await seed(db)
    admin = await make_staff(db, "admin")
    body = await get(client, admin, **params)
    assert body["total"] == expected == len(body["items"])


async def test_pagination(client: AsyncClient, db: AsyncSession) -> None:
    for request_id in range(1, 6):
        audit.record(db, "STATUS_CHANGED", entity_type="request", entity_id=request_id)
    await db.commit()
    admin = await make_staff(db, "admin")
    # Кожен перегляд додає AUDIT_VIEWED, тому сторінки рахуємо за дією STATUS_CHANGED.
    pages = [
        await get(client, admin, action="STATUS_CHANGED", limit=2, offset=offset)
        for offset in (0, 2, 4)
    ]
    assert all(page["total"] == 5 for page in pages)
    assert [len(page["items"]) for page in pages] == [2, 2, 1]
    seen = [i["entity_id"] for page in pages for i in page["items"]]
    assert seen == [5, 4, 3, 2, 1]  # сторінки не перетинаються, новіші спершу


async def test_date_range(client: AsyncClient, db: AsyncSession) -> None:
    await seed(db)
    admin = await make_staff(db, "admin")
    now = datetime.now(UTC)
    past = await get(client, admin, date_to=(now - timedelta(days=1)).isoformat())
    recent = await get(
        client, admin, action="STATUS_CHANGED", date_from=(now - timedelta(hours=1)).isoformat()
    )
    assert past["total"] == 0
    assert recent["total"] == 2


async def test_date_from_after_date_to(client: AsyncClient, db: AsyncSession) -> None:
    admin = await make_staff(db, "admin")
    now = datetime.now(UTC)
    response = await client.get(
        URL,
        params={"date_from": now.isoformat(), "date_to": (now - timedelta(days=1)).isoformat()},
        headers=auth(admin),
    )
    assert response.status_code == 422


async def test_correlation_id_groups_one_request(client: AsyncClient, db: AsyncSession) -> None:
    """Відмова водію пише ACCESS_DENIED з correlation_id = X-Request-ID; за ним його і знайдемо."""
    driver = await make_driver(db)
    denied = await client.get(URL, headers=auth(driver))
    assert denied.status_code == 403

    admin = await make_staff(db, "admin")
    body = await get(client, admin, correlation_id=denied.headers["X-Request-ID"])
    assert body["total"] == 1
    assert body["items"][0]["action"] == "ACCESS_DENIED"
    assert body["items"][0]["ip"] is not None


async def test_view_is_audited_with_filters(client: AsyncClient, db: AsyncSession) -> None:
    """Перегляд журналу сам фіксується (AUDIT_VIEWED) разом із фільтрами."""
    dg = await make_staff(db, "data_governance")
    await get(client, dg, action="LOGIN_FAILED", limit=10)

    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "AUDIT_VIEWED"))
    assert entry.actor_id == dg.id and entry.actor_role == "data_governance"
    assert entry.new_value == {"action": "LOGIN_FAILED", "limit": 10, "offset": 0, "total": 0}


@pytest.mark.parametrize("role", ["dispatcher", "contractor"])
async def test_other_roles_denied(client: AsyncClient, db: AsyncSession, role: str) -> None:
    user = await make_staff(db, role)
    assert (await client.get(URL, headers=auth(user))).status_code == 403


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
async def test_limits_validated(client: AsyncClient, db: AsyncSession, params: dict) -> None:
    admin = await make_staff(db, "admin")
    assert (await client.get(URL, params=params, headers=auth(admin))).status_code == 422


async def test_report_lifecycle_visible_in_audit(client: AsyncClient, db: AsyncSession) -> None:
    """Наскрізно: створення заявки й зміна статусу знаходяться фільтром по заявці."""
    from tests.test_reports_status import WEST, new_report, patch

    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, report["id"], status="accepted")

    admin = await make_staff(db, "admin")
    body = await get(client, admin, entity_type="request", entity_id=report["id"])
    assert [i["action"] for i in body["items"]] == ["STATUS_CHANGED", "REPORT_CREATED"]
