"""Зміна статусу заявки: PATCH /reports/{id}/status (KAN-59, UC-02, UC-04, БП-3, БП-6)."""

from datetime import date, timedelta
from itertools import count

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ServiceKind
from app.modules.audit.models import AuditLog
from app.modules.reports.models import Request, StatusHistory
from app.modules.users.models import User
from tests.factories import auth, make_contractor, make_driver, make_staff

URL = "/api/v1/reports"
WEST_POINT = {"latitude": 49.84, "longitude": 23.98}
EAST_POINT = {"latitude": 49.84, "longitude": 24.08}
WEST = "Комунальна служба Залізничного району (демо)"
EAST = "Комунальна служба Шевченківського району (демо)"
POLICE = "Дорожня поліція (демо)"
_emails = count(1)


async def new_report(
    client: AsyncClient, db: AsyncSession, problem_type: str = "pothole", point: dict | None = None
) -> dict:
    driver = await make_driver(db, email=f"driver{next(_emails)}@test.ua")
    response = await client.post(
        URL, data={"problem_type": problem_type, **(point or WEST_POINT)}, headers=auth(driver)
    )
    assert response.status_code == 201, response.text
    return {**response.json(), "author": driver}


async def patch(client: AsyncClient, user: User, report_id: int, **body) -> Response:
    return await client.patch(f"{URL}/{report_id}/status", json=body, headers=auth(user))


async def history(db: AsyncSession, report_id: int) -> list[StatusHistory]:
    rows = await db.scalars(
        select(StatusHistory)
        .where(StatusHistory.request_id == report_id)
        .order_by(StatusHistory.id)
    )
    return list(rows)


# ---------- основний сценарій ----------


async def test_full_cycle_by_service(client: AsyncClient, db: AsyncSession) -> None:
    """UC-02: «Нова» → «Прийнята» → «В роботі» → «Усунена» власними силами служби."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)

    for target in ("accepted", "in_progress", "resolved"):
        response = await patch(client, dispatcher, report["id"], status=target)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target

    body = response.json()
    assert body["previous_status"] == "in_progress"
    assert body["closed_at"] is not None  # кінцевий статус закриває заявку
    assert body["next_statuses"] == []

    steps = [(h.from_status, h.to_status) for h in await history(db, report["id"])]
    assert steps == [
        (None, "new"),
        ("new", "accepted"),
        ("accepted", "in_progress"),
        ("in_progress", "resolved"),
    ]
    assert all(h.changed_by == dispatcher.id for h in (await history(db, report["id"]))[1:])


async def test_accept_with_deadline_and_comment(client: AsyncClient, db: AsyncSession) -> None:
    """UC-02, крок 4: строк і коментар для водія."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    deadline = date.today() + timedelta(days=3)

    response = await patch(
        client,
        dispatcher,
        report["id"],
        status="accepted",
        deadline=deadline.isoformat(),
        comment="Бригада виїде протягом 3 днів",
    )
    assert response.status_code == 200, response.text
    assert response.json()["deadline"] == deadline.isoformat()
    assert set(response.json()["next_statuses"]) == {"in_progress", "rejected"}

    request = await db.get(Request, report["id"])
    assert request.deadline == deadline and request.closed_at is None
    assert (await history(db, report["id"]))[-1].comment == "Бригада виїде протягом 3 днів"


async def test_change_written_to_audit(client: AsyncClient, db: AsyncSession) -> None:
    """QR-13: зміна статусу фіксує, хто, коли і що змінив."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, report["id"], status="accepted")

    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "STATUS_CHANGED"))
    assert entry.actor_id == dispatcher.id
    assert entry.actor_role == "dispatcher"
    assert (entry.entity_type, entry.entity_id) == ("request", report["id"])
    assert entry.old_value == {"status": "new"}
    assert entry.new_value["status"] == "accepted"
    assert entry.new_value["number"] == report["number"]


# ---------- відхилення (БП-3) ----------


async def test_reject_requires_reason(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)

    response = await patch(client, dispatcher, report["id"], status="rejected", reject_reason=" ")
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "reject_reason"]
    assert (await db.get(Request, report["id"])).status == "new"  # статус не змінився


async def test_reject_with_reason(client: AsyncClient, db: AsyncSession) -> None:
    """UC-02 A2: автор отримує причину - вона є в заявці й у таймлайні."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)

    response = await patch(
        client, dispatcher, report["id"], status="rejected", reject_reason="Вже в плані ремонтів"
    )
    assert response.status_code == 200, response.text
    assert response.json()["reject_reason"] == "Вже в плані ремонтів"
    assert response.json()["closed_at"] is not None
    assert (await history(db, report["id"]))[-1].comment == "Вже в плані ремонтів"


async def test_reject_after_accept(client: AsyncClient, db: AsyncSession) -> None:
    """Відхилення після перевірки на місці («не підтверджено на місці»)."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, report["id"], status="accepted")
    response = await patch(
        client, dispatcher, report["id"], status="rejected", reject_reason="Не підтверджено"
    )
    assert response.status_code == 200


async def test_reason_only_for_reject(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    response = await patch(
        client, dispatcher, report["id"], status="accepted", reject_reason="Помилково"
    )
    assert response.status_code == 422


# ---------- недопустимі переходи ----------


@pytest.mark.parametrize("target", ["in_progress", "resolved", "done", "new"])
async def test_invalid_transition_from_new(
    client: AsyncClient, db: AsyncSession, target: str
) -> None:
    """«Інші переходи система відхиляє помилкою» (п. 2.2) - 409 і статус не змінюється."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)

    response = await patch(client, dispatcher, report["id"], status=target)
    assert response.status_code == 409
    assert (await db.get(Request, report["id"])).status == "new"
    assert len(await history(db, report["id"])) == 1


async def test_closed_report_cannot_change(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    await patch(client, dispatcher, report["id"], status="rejected", reject_reason="Дубль")

    response = await patch(client, dispatcher, report["id"], status="accepted")
    assert response.status_code == 409
    assert "недопустимий" in response.json()["detail"]


async def test_deadline_in_past(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    response = await patch(client, dispatcher, report["id"], status="accepted", deadline=yesterday)
    assert response.status_code == 422


async def test_unknown_status_value(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    response = await patch(client, dispatcher, report["id"], status="closed")
    assert response.status_code == 422


async def test_not_found(client: AsyncClient, db: AsyncSession) -> None:
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    response = await patch(client, dispatcher, 999_999, status="accepted")
    assert response.status_code == 404


# ---------- права (RBAC, БП-6) ----------


@pytest.mark.parametrize("role", ["driver", "admin", "data_governance"])
async def test_roles_without_policy(client: AsyncClient, db: AsyncSession, role: str) -> None:
    report = await new_report(client, db)
    user = report["author"] if role == "driver" else await make_staff(db, role)
    response = await patch(client, user, report["id"], status="accepted")
    assert response.status_code == 403


async def test_other_district_service_denied(client: AsyncClient, db: AsyncSession) -> None:
    """Заявка західного району: диспетчер східного району її не змінює (scope service)."""
    report = await new_report(client, db)
    other = await make_staff(db, "dispatcher", service_name=EAST)

    response = await patch(client, other, report["id"], status="accepted")
    assert response.status_code == 403
    denied = await db.scalar(select(AuditLog).where(AuditLog.action == "ACCESS_DENIED"))
    assert denied.entity_id == report["id"]


async def test_copy_service_cannot_change_status(client: AsyncClient, db: AsyncSession) -> None:
    """Перешкода: основна служба - поліція, комунальна служба отримала копію.
    Копія заявку бачить, але статус змінює лише основна служба."""
    report = await new_report(client, db, "obstacle")
    communal = await make_staff(db, "dispatcher", service_name=WEST)
    police = await make_staff(db, "dispatcher", service_name=POLICE)

    assert (await patch(client, communal, report["id"], status="accepted")).status_code == 403
    assert (await patch(client, police, report["id"], status="accepted")).status_code == 200


# ---------- підрядник (UC-04) ----------


async def assign(db: AsyncSession, report_id: int, contractor: User) -> None:
    """Призначення підрядника - задача KAN-62; тут ставимо contractor_id напряму."""
    await db.execute(
        update(Request)
        .where(Request.id == report_id)
        .values(contractor_id=contractor.contractor_id)
    )
    await db.commit()


async def test_contractor_cycle(client: AsyncClient, db: AsyncSession) -> None:
    """UC-04: підрядник «В роботі» → «Виконана», диспетчер підтверджує «Усунена»."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    contractor = await make_contractor(db)
    await patch(client, dispatcher, report["id"], status="accepted")
    await assign(db, report["id"], contractor)

    assert (await patch(client, contractor, report["id"], status="in_progress")).status_code == 200
    done = await patch(client, contractor, report["id"], status="done")
    assert done.status_code == 200
    assert done.json()["next_statuses"] == []  # далі - лише служба

    resolved = await patch(client, dispatcher, report["id"], status="resolved")
    assert resolved.status_code == 200


async def test_contractor_cannot_resolve(client: AsyncClient, db: AsyncSession) -> None:
    """БП-6, UC-04 E2: підрядник ставить «Усунена» - відмова 403 і запис в аудит."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    contractor = await make_contractor(db)
    await patch(client, dispatcher, report["id"], status="accepted")
    await assign(db, report["id"], contractor)
    await patch(client, contractor, report["id"], status="in_progress")
    await patch(client, contractor, report["id"], status="done")

    response = await patch(client, contractor, report["id"], status="resolved")
    assert response.status_code == 403
    assert "Усунена" in response.json()["detail"]
    denied = await db.scalar(select(AuditLog).where(AuditLog.action == "ACCESS_DENIED"))
    assert denied.new_value["reason"] == "transition:done->resolved"


async def test_service_waits_for_contractor(client: AsyncClient, db: AsyncSession) -> None:
    """Якщо роботи виконує підрядник, служба не закриває заявку до його «Виконана»."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    contractor = await make_contractor(db)
    await patch(client, dispatcher, report["id"], status="accepted")
    await assign(db, report["id"], contractor)
    await patch(client, contractor, report["id"], status="in_progress")

    response = await patch(client, dispatcher, report["id"], status="resolved")
    assert response.status_code == 409
    assert "Виконана" in response.json()["detail"]


async def test_foreign_contractor_denied(client: AsyncClient, db: AsyncSession) -> None:
    """БП-5: підрядник не бачить і не змінює чужі роботи."""
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    assigned = await make_contractor(db, "Призначений")
    stranger = await make_contractor(db, "Чужий")
    await patch(client, dispatcher, report["id"], status="accepted")
    await assign(db, report["id"], assigned)

    response = await patch(client, stranger, report["id"], status="in_progress")
    assert response.status_code == 403


async def test_police_changes_accident(client: AsyncClient, db: AsyncSession) -> None:
    """Аварію опрацьовує поліція (основна служба після KAN-58)."""
    report = await new_report(client, db, "accident", EAST_POINT)
    police = await make_staff(db, "operator", ServiceKind.POLICE)
    response = await patch(client, police, report["id"], status="accepted")
    assert response.status_code == 200
