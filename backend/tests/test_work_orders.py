"""Підрядні роботи (KAN-62; UC-04, UC-06; F-19, F-20; БП-5, БП-6)."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PhotoKind
from app.modules.audit.models import AuditLog
from app.modules.reports.models import Photo, Request
from app.modules.users.models import User
from tests.factories import auth, make_contractor, make_driver, make_staff
from tests.test_reports_photos import image_bytes
from tests.test_reports_status import WEST, new_report, patch

URL = "/api/v1/work-orders"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


async def accepted_report(client: AsyncClient, db: AsyncSession) -> dict:
    report = await new_report(client, db)
    dispatcher = await make_staff(db, "dispatcher", service_name=WEST)
    assert (await patch(client, dispatcher, report["id"], status="accepted")).status_code == 200
    return {**report, "dispatcher": dispatcher}


async def assign(
    client: AsyncClient, admin: User, request_id: int, contractor: User, **extra
) -> Response:
    body = {
        "request_id": request_id,
        "contractor_id": contractor.contractor_id,
        "deadline": TOMORROW,
        **extra,
    }
    return await client.post(URL, json=body, headers=auth(admin))


async def in_progress(client: AsyncClient, db: AsyncSession) -> tuple[dict, User, User]:
    """Заявка «В роботі» з призначеним підрядником. Повертає (заявка, підрядник, адмін)."""
    report = await accepted_report(client, db)
    admin = await make_staff(db, "admin")
    contractor = await make_contractor(db)
    assert (await assign(client, admin, report["id"], contractor)).status_code == 201
    assert (await patch(client, contractor, report["id"], status="in_progress")).status_code == 200
    return report, contractor, admin


async def progress(
    client: AsyncClient,
    user: User,
    request_id: int,
    percent: int,
    photos: int = 0,
    act: tuple[str, bytes, str] | None = None,
    comment: str | None = None,
) -> Response:
    files = [("photos", (f"after{i}.jpg", image_bytes(), "image/jpeg")) for i in range(photos)]
    if act:
        files.append(("act", act))
    data = {"progress_percent": str(percent)}
    if comment:
        data["comment"] = comment
    return await client.post(
        f"{URL}/{request_id}/progress", data=data, files=files or None, headers=auth(user)
    )


# ---------- призначення (F-19, UC-04 кроки 1-2) ----------


async def test_admin_assigns_contractor(client: AsyncClient, db: AsyncSession) -> None:
    report = await accepted_report(client, db)
    admin = await make_staff(db, "admin")
    contractor = await make_contractor(db)

    response = await assign(client, admin, report["id"], contractor, scope="Ремонт 12 м²")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["contractor_id"] == contractor.contractor_id
    assert body["contractor_name"] == contractor.full_name
    assert body["deadline"] == TOMORROW
    assert body["is_overdue"] is False
    assert "author_id" not in body  # БП-5: даних водія немає

    event = await db.scalar(select(AuditLog).where(AuditLog.action == "WORK_ASSIGNED"))
    assert event.entity_id == report["id"]
    assert event.new_value["scope"] == "Ремонт 12 м²"


@pytest.mark.parametrize("role", ["driver", "dispatcher", "data_governance"])
async def test_only_admin_can_assign(client: AsyncClient, db: AsyncSession, role: str) -> None:
    report = await accepted_report(client, db)
    contractor = await make_contractor(db)
    user = await make_driver(db) if role == "driver" else await make_staff(db, role)
    assert (await assign(client, user, report["id"], contractor)).status_code == 403


async def test_assign_requires_accepted_status(client: AsyncClient, db: AsyncSession) -> None:
    report = await new_report(client, db)  # статус «Нова»
    admin = await make_staff(db, "admin")
    contractor = await make_contractor(db)
    response = await assign(client, admin, report["id"], contractor)
    assert response.status_code == 409


async def test_assign_unknown_request_and_contractor(client: AsyncClient, db: AsyncSession) -> None:
    report = await accepted_report(client, db)
    admin = await make_staff(db, "admin")
    contractor = await make_contractor(db)
    assert (await assign(client, admin, 999999, contractor)).status_code == 404
    body = {"request_id": report["id"], "contractor_id": 999999, "deadline": TOMORROW}
    response = await client.post(URL, json=body, headers=auth(admin))
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "contractor_id"]


async def test_assign_deadline_in_past(client: AsyncClient, db: AsyncSession) -> None:
    report = await accepted_report(client, db)
    admin = await make_staff(db, "admin")
    contractor = await make_contractor(db)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    response = await assign(client, admin, report["id"], contractor, deadline=yesterday)
    assert response.status_code == 422


async def test_reassign_revokes_old_contractor(client: AsyncClient, db: AsyncSession) -> None:
    """UC-04, A1: зміна підрядника - попередній одразу втрачає доступ (БП-5)."""
    report, old, admin = await in_progress(client, db)
    new = await make_contractor(db, "Новий підрядник")

    assert (await assign(client, admin, report["id"], new)).status_code == 201
    assert (await progress(client, old, report["id"], 10)).status_code == 403
    assert (await progress(client, new, report["id"], 10)).status_code == 200


# ---------- список «Мої об'єкти» (F-20) ----------


async def test_contractor_sees_only_own(client: AsyncClient, db: AsyncSession) -> None:
    report, contractor, admin = await in_progress(client, db)
    other = await make_contractor(db, "Інший підрядник")

    mine = await client.get(URL, headers=auth(contractor))
    assert [item["id"] for item in mine.json()] == [report["id"]]
    assert (await client.get(URL, headers=auth(other))).json() == []
    assert len((await client.get(URL, headers=auth(admin))).json()) == 1


async def test_list_status_filter_and_roles(client: AsyncClient, db: AsyncSession) -> None:
    report, contractor, admin = await in_progress(client, db)
    done = await client.get(f"{URL}?status=done", headers=auth(admin))
    assert done.json() == []
    driver = await make_driver(db, email="d-list@test.ua")
    assert (await client.get(URL, headers=auth(driver))).status_code == 403
    assert (await client.get(URL)).status_code == 401


async def test_service_sees_own_service_only(client: AsyncClient, db: AsyncSession) -> None:
    report, _, _ = await in_progress(client, db)
    own = report["dispatcher"]
    east = await make_staff(
        db, "dispatcher", service_name="Комунальна служба Шевченківського району (демо)"
    )
    assert len((await client.get(URL, headers=auth(own))).json()) == 1
    assert (await client.get(URL, headers=auth(east))).json() == []


async def test_overdue_flag(client: AsyncClient, db: AsyncSession) -> None:
    """UC-04, A1: строк минув, роботи не завершено - позначка «прострочено»."""
    report, contractor, _ = await in_progress(client, db)
    await db.execute(
        update(Request)
        .where(Request.id == report["id"])
        .values(deadline=date.today() - timedelta(days=2))
    )
    await db.commit()
    item = (await client.get(URL, headers=auth(contractor))).json()[0]
    assert item["is_overdue"] is True


# ---------- прогрес і акт (F-20, UC-06) ----------


async def test_progress_update(client: AsyncClient, db: AsyncSession) -> None:
    report, contractor, _ = await in_progress(client, db)
    response = await progress(client, contractor, report["id"], 40, photos=1, comment="Асфальт")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["progress_percent"], body["photos_added"], body["submitted"]) == (40, 1, False)
    assert body["status"] == "in_progress"
    kinds = list(await db.scalars(select(Photo.kind).where(Photo.request_id == report["id"])))
    assert PhotoKind.AFTER in kinds
    event = await db.scalar(select(AuditLog).where(AuditLog.action == "WORK_PROGRESS_UPDATED"))
    assert event.old_value == {"progress_percent": 0}
    assert event.new_value["progress_percent"] == 40


async def test_progress_cannot_decrease(client: AsyncClient, db: AsyncSession) -> None:
    report, contractor, _ = await in_progress(client, db)
    await progress(client, contractor, report["id"], 60)
    response = await progress(client, contractor, report["id"], 30)
    assert response.status_code == 422


@pytest.mark.parametrize("percent", [-1, 101])
async def test_progress_range(client: AsyncClient, db: AsyncSession, percent: int) -> None:
    report, contractor, _ = await in_progress(client, db)
    assert (await progress(client, contractor, report["id"], percent)).status_code == 422


async def test_progress_requires_in_progress_status(client: AsyncClient, db: AsyncSession) -> None:
    report = await accepted_report(client, db)  # ще «Прийнята»
    admin = await make_staff(db, "admin")
    contractor = await make_contractor(db)
    await assign(client, admin, report["id"], contractor)
    assert (await progress(client, contractor, report["id"], 10)).status_code == 409


async def test_submit_requires_photo_and_act(client: AsyncClient, db: AsyncSession) -> None:
    """БП-6: при 100 % без фото «після» й акта роботи не здаються."""
    report, contractor, _ = await in_progress(client, db)
    no_photo = await progress(client, contractor, report["id"], 100)
    assert no_photo.status_code == 422
    assert no_photo.json()["detail"][0]["loc"] == ["body", "photos"]
    no_act = await progress(client, contractor, report["id"], 100, photos=1)
    assert no_act.status_code == 422
    assert no_act.json()["detail"][0]["loc"] == ["body", "act"]
    # нічого не збереглось і статус не змінився
    assert await db.scalar(select(Photo.id).where(Photo.request_id == report["id"])) is None
    await db.refresh(await db.get(Request, report["id"]))
    assert (await db.get(Request, report["id"])).status.value == "in_progress"


async def test_submit_full_cycle(client: AsyncClient, db: AsyncSession) -> None:
    """UC-06: 100 % + фото «після» + акт PDF -> «Виконана»; службі лишається «Усунена»."""
    report, contractor, _ = await in_progress(client, db)
    response = await progress(
        client, contractor, report["id"], 100, photos=1, act=("act.pdf", PDF, "application/pdf")
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["submitted"], body["act_attached"]) == ("done", True, True)

    mime = list(await db.scalars(select(Photo.mime_type).where(Photo.kind == PhotoKind.ACT)))
    assert mime == ["application/pdf"]
    changed = list(await db.scalars(select(AuditLog).where(AuditLog.action == "STATUS_CHANGED")))
    assert changed[-1].new_value["status"] == "done"

    resolved = await patch(client, report["dispatcher"], report["id"], status="resolved")
    assert resolved.status_code == 200


async def test_act_and_photo_can_come_in_separate_requests(
    client: AsyncClient, db: AsyncSession
) -> None:
    report, contractor, _ = await in_progress(client, db)
    await progress(client, contractor, report["id"], 70, photos=1)
    response = await progress(
        client, contractor, report["id"], 100, act=("act.pdf", PDF, "application/pdf")
    )
    assert response.status_code == 200
    assert response.json()["submitted"] is True


async def test_invalid_act_rejected(client: AsyncClient, db: AsyncSession) -> None:
    report, contractor, _ = await in_progress(client, db)
    response = await progress(
        client, contractor, report["id"], 100, photos=1, act=("act.pdf", b"not a pdf", "text/plain")
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "act"]


async def test_foreign_contractor_cannot_update(client: AsyncClient, db: AsyncSession) -> None:
    """UC-04 E1, БП-5: чужа робота - 403 і запис ACCESS_DENIED."""
    report, _, _ = await in_progress(client, db)
    stranger = await make_contractor(db, "Чужий підрядник")
    response = await progress(client, stranger, report["id"], 10)
    assert response.status_code == 403
    denied = await db.scalar(select(AuditLog).where(AuditLog.action == "ACCESS_DENIED"))
    assert denied.new_value["reason"] == "out_of_scope:own"


async def test_other_roles_cannot_update_progress(client: AsyncClient, db: AsyncSession) -> None:
    report, _, admin = await in_progress(client, db)
    assert (await progress(client, admin, report["id"], 10)).status_code == 403
    assert (await progress(client, report["dispatcher"], report["id"], 10)).status_code == 403


async def test_progress_unknown_request(client: AsyncClient, db: AsyncSession) -> None:
    contractor = await make_contractor(db)
    assert (await progress(client, contractor, 999999, 10)).status_code == 404
