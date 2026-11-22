"""Таймлайн статусів: GET /reports/{id}/history (KAN-59, UC-03 крок 4, табл. 18)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from app.modules.reports.models import Request
from tests.factories import auth, make_contractor, make_driver, make_staff
from tests.test_reports_status import EAST, POLICE, WEST, new_report, patch

URL = "/api/v1/reports"


def history_url(report_id: int) -> str:
    return f"{URL}/{report_id}/history"


async def test_driver_sees_own_timeline(client: AsyncClient, db: AsyncSession) -> None:
    """UC-03: водій бачить таймлайн і причину відхилення, але не бачить, хто з
    працівників змінив статус (внутрішні дані, табл. 11)."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, report["id"], status="accepted", comment="Виїдемо завтра")
    await patch(
        client, dispatcher, report["id"], status="rejected", reject_reason="Не підтверджено"
    )

    response = await client.get(history_url(report["id"]), headers=auth(report["author"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["number"] == report["number"] and body["status"] == "rejected"
    assert [i["to_status"] for i in body["items"]] == ["new", "accepted", "rejected"]
    assert [i["to_label"] for i in body["items"]] == ["Нова", "Прийнята", "Відхилена"]
    assert body["items"][0]["from_status"] is None
    assert body["items"][1]["comment"] == "Виїдемо завтра"
    assert body["items"][2]["comment"] == "Не підтверджено"
    assert all(i["changed_by"] is None for i in body["items"])


async def test_dispatcher_sees_who_changed(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, report["id"], status="accepted")

    body = (await client.get(history_url(report["id"]), headers=auth(dispatcher))).json()
    assert body["items"][-1]["changed_by"] == dispatcher.id


async def test_other_driver_denied(client: AsyncClient, db: AsyncSession) -> None:
    """Чужу заявку водій не бачить: 403 і ACCESS_DENIED в аудиті."""
    report = await new_report(client, db)
    stranger = await make_driver(db, email="stranger@test.ua")

    response = await client.get(history_url(report["id"]), headers=auth(stranger))
    assert response.status_code == 403
    denied = await db.scalar(select(AuditLog).where(AuditLog.action == "ACCESS_DENIED"))
    assert denied.new_value["reason"] == "out_of_scope:own"


async def test_other_district_denied(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    other = await make_staff(db, "dispatcher", service_name=EAST)
    assert (await client.get(history_url(report["id"]), headers=auth(other))).status_code == 403


async def test_copy_service_can_view(client: AsyncClient, db: AsyncSession) -> None:
    """Перешкода: комунальна служба отримала копію - таймлайн бачить."""
    report = await new_report(client, db, "obstacle")
    police = await make_staff(db, "dispatcher", service_name=POLICE)
    communal = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, police, report["id"], status="accepted")

    response = await client.get(history_url(report["id"]), headers=auth(communal))
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


async def test_admin_sees_any(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    admin = await make_staff(db, "admin")
    assert (await client.get(history_url(report["id"]), headers=auth(admin))).status_code == 200


async def test_contractor_only_assigned(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    contractor = await make_contractor(db)
    response = await client.get(history_url(report["id"]), headers=auth(contractor))
    assert response.status_code == 403

    await db.execute(
        update(Request)
        .where(Request.id == report["id"])
        .values(contractor_id=contractor.contractor_id)
    )
    await db.commit()
    response = await client.get(history_url(report["id"]), headers=auth(contractor))
    assert response.status_code == 200


@pytest.mark.parametrize("role", ["data_governance"])
async def test_role_without_policy(client: AsyncClient, db: AsyncSession, role: str) -> None:
    report = await new_report(client, db)
    user = await make_staff(db, role)
    assert (await client.get(history_url(report["id"]), headers=auth(user))).status_code == 403


async def test_anonymous_401(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    assert (await client.get(history_url(report["id"]))).status_code == 401


async def test_not_found(client: AsyncClient, db: AsyncSession) -> None:
    admin = await make_staff(db, "admin")
    assert (await client.get(history_url(999_999), headers=auth(admin))).status_code == 404


async def test_history_matches_request_status(client: AsyncClient, db: AsyncSession) -> None:
    """Останній запис таймлайну завжди збігається з поточним статусом заявки."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    for target in ("accepted", "in_progress"):
        await patch(client, dispatcher, report["id"], status=target)

    last = await db.scalar(
        text(
            "SELECT to_status FROM status_history WHERE request_id = :r "
            "ORDER BY changed_at DESC, id DESC LIMIT 1"
        ),
        {"r": report["id"]},
    )
    assert last == (await db.get(Request, report["id"])).status == "in_progress"
