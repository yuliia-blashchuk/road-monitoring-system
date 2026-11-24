"""QA KAN-73: тест-кейси API маршрутизації та статусів заявки.

Перевірки йдуть через HTTP так, як працює фронтенд: POST /reports,
PATCH /reports/{id}/status, GET /reports/{id}/history. Очікувані результати записані
тут окремо від коду - таблиця маршрутизації (міграція 0004, KAN-58) і таблиця переходів
(п. 2.2, KAN-59). Тому тест помітить, якщо правила в коді зміняться без зміни вимог.

Таблиця тест-кейсів: docs/testing/KAN-73-api-routing-status.md.
"""

from itertools import count

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models import ProblemType, Service
from app.modules.audit.models import AuditLog
from app.modules.reports.models import Request, StatusHistory
from app.modules.routing.models import RoutingRule
from app.modules.users.models import User
from tests.factories import auth, make_contractor, make_driver, make_staff
from tests.test_reports_status import submit_work

URL = "/api/v1/reports"
WEST = "Комунальна служба Залізничного району (демо)"
EAST = "Комунальна служба Шевченківського району (демо)"
POLICE = "Дорожня поліція (демо)"
DISTRICT = "district"  # комунальна служба того району, де лежить точка

ZONES = {
    "west": ({"latitude": 49.84, "longitude": 23.98}, WEST),
    "east": ({"latitude": 49.84, "longitude": 24.08}, EAST),
}

# Таблиця маршрутизації (KAN-58): тип -> (основна служба, копія, початковий пріоритет).
ROUTING_TABLE = {
    "pothole": (DISTRICT, None, "medium"),
    "damaged_surface": (DISTRICT, None, "low"),
    "traffic_light": (DISTRICT, None, "high"),
    "other": (DISTRICT, None, "low"),
    "accident": (POLICE, DISTRICT, "critical"),
    "obstacle": (POLICE, DISTRICT, "high"),
}

STATUSES = ["new", "accepted", "in_progress", "done", "resolved", "rejected"]

# Допустимі переходи (п. 2.2) і роль, яка їх виконує в тесті.
ALLOWED = {
    ("new", "accepted"): "dispatcher",
    ("new", "rejected"): "dispatcher",
    ("accepted", "rejected"): "dispatcher",
    ("accepted", "in_progress"): "dispatcher",
    ("in_progress", "resolved"): "dispatcher",
    ("in_progress", "done"): "contractor",
    ("done", "resolved"): "dispatcher",
}
INVALID = [(s, t) for s in STATUSES for t in STATUSES if (s, t) not in ALLOWED]

# Переходи, які роблять не через PATCH /status, а окремою дією (KAN-121):
# «Виконана» - здача робіт з прогресом 100 %, фото «після» й актом.
WORK_ORDER_ONLY = {("in_progress", "done")}

# Як довести заявку до потрібного статусу: (хто, статус).
PATHS = {
    "new": [],
    "accepted": [("dispatcher", "accepted")],
    "rejected": [("dispatcher", "rejected")],
    "in_progress": [("dispatcher", "accepted"), ("dispatcher", "in_progress")],
    "resolved": [
        ("dispatcher", "accepted"),
        ("dispatcher", "in_progress"),
        ("dispatcher", "resolved"),
    ],
    "done": [("dispatcher", "accepted"), ("contractor", "in_progress"), ("contractor", "submit")],
}

_emails = count(1)


# ---------- допоміжні функції ----------


async def create_report(
    client: AsyncClient, db: AsyncSession, problem_type: str, point: dict
) -> Response:
    driver = await make_driver(db, email=f"kan73-{next(_emails)}@test.ua")
    return await client.post(
        URL, data={"problem_type": problem_type, **point}, headers=auth(driver)
    )


async def patch(client: AsyncClient, user: User, report_id: int, status: str) -> Response:
    body = {"status": status}
    if status == "rejected":
        body["reject_reason"] = "Не підтверджено на місці"
    return await client.patch(f"{URL}/{report_id}/status", json=body, headers=auth(user))


async def count_rows(db: AsyncSession, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


async def status_changes(db: AsyncSession, report_id: int) -> int:
    return await count_rows(
        db, AuditLog, AuditLog.action == "STATUS_CHANGED", AuditLog.entity_id == report_id
    )


async def fresh(db: AsyncSession, report_id: int) -> Request:
    return await db.scalar(
        select(Request).where(Request.id == report_id).execution_options(populate_existing=True)
    )


class Actors:
    """Диспетчер західного району і підрядник - ті, хто змінює статуси в тестах."""

    def __init__(self, dispatcher: User, contractor: User) -> None:
        self.by_role = {"dispatcher": dispatcher, "contractor": contractor}

    @classmethod
    async def create(cls, db: AsyncSession) -> "Actors":
        return cls(await make_staff(db, "dispatcher", service_name=WEST), await make_contractor(db))


async def assign_contractor(db: AsyncSession, actors: Actors, report_id: int) -> None:
    """Призначення підрядника - KAN-62; тут ставимо contractor_id напряму."""
    await db.execute(
        update(Request)
        .where(Request.id == report_id)
        .values(contractor_id=actors.by_role["contractor"].contractor_id)
    )
    await db.commit()


async def report_in_status(
    client: AsyncClient, db: AsyncSession, actors: Actors, status: str
) -> int:
    """Створює заявку (яма, західний район) і доводить її до статусу status через API."""
    response = await create_report(client, db, "pothole", ZONES["west"][0])
    assert response.status_code == 201, response.text
    report_id = response.json()["id"]
    for role, target in PATHS[status]:
        if role == "contractor":
            await assign_contractor(db, actors, report_id)
        if target == "submit":
            step = await submit_work(client, actors.by_role[role], report_id)
        else:
            step = await patch(client, actors.by_role[role], report_id, target)
        assert step.status_code == 200, step.text
    return report_id


# ---------- маршрутизація ----------


@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("problem_type", ROUTING_TABLE)
async def test_routing_table(
    client: AsyncClient, db: AsyncSession, problem_type: str, zone: str
) -> None:
    """TC-API-01: кожен тип проблеми в кожному районі потрапляє за таблицею маршрутизації."""
    point, district = ZONES[zone]
    service, copy, priority = ROUTING_TABLE[problem_type]
    service = district if service == DISTRICT else service
    copy = district if copy == DISTRICT else copy

    response = await create_report(client, db, problem_type, point)
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["service"], body["copy_service"], body["priority"]) == (service, copy, priority)
    assert body["status"] == "new"

    # Те саме збережено в БД, а в журналі вказано правило, за яким обрано службу.
    request = await db.get(Request, body["id"])
    assert await db.scalar(select(Service.name).where(Service.id == request.service_id)) == service
    rule_id = await db.scalar(
        select(RoutingRule.id)
        .join(ProblemType, ProblemType.id == RoutingRule.problem_type_id)
        .where(ProblemType.code == problem_type, RoutingRule.service_id == request.service_id)
    )
    entry = await db.scalar(
        select(AuditLog).where(
            AuditLog.action == "REPORT_CREATED", AuditLog.entity_id == body["id"]
        )
    )
    assert entry.new_value["routing_rule_id"] == rule_id
    assert await count_rows(db, StatusHistory, StatusHistory.request_id == body["id"]) == 1


@pytest.mark.parametrize(
    ("longitude", "expected"), [(24.025, WEST), (24.035, EAST)], ids=["west-side", "east-side"]
)
async def test_points_near_district_border(
    client: AsyncClient, db: AsyncSession, longitude: float, expected: str
) -> None:
    """TC-API-02: точки поруч із межею районів (24.03) потрапляють у службу свого боку."""
    response = await create_report(
        client, db, "pothole", {"latitude": 49.84, "longitude": longitude}
    )
    assert response.status_code == 201
    assert response.json()["service"] == expected


@pytest.mark.xfail(
    strict=True,
    reason="Дефект KAN-73-D1: точка рівно на межі районів не входить у жодну зону "
    "(ST_Contains не враховує межу), тому заявка лишається без служби",
)
async def test_point_on_district_border(client: AsyncClient, db: AsyncSession) -> None:
    """TC-API-03: заявка рівно на межі районів має отримати службу одного з районів."""
    response = await create_report(client, db, "pothole", {"latitude": 49.84, "longitude": 24.03})
    assert response.status_code == 201
    assert response.json()["service"] in (WEST, EAST)


@pytest.mark.parametrize(
    "point",
    [{"latitude": 50.4501, "longitude": 30.5234}, {"latitude": 49.84, "longitude": 24.20}],
    ids=["kyiv", "east-of-city"],
)
async def test_point_outside_city(client: AsyncClient, db: AsyncSession, point: dict) -> None:
    """TC-API-04: точка поза межами міста - 422, заявка не створюється (DQ-03, E2)."""
    response = await create_report(client, db, "accident", point)
    assert response.status_code == 422
    assert "обслуговується" in response.text
    assert await count_rows(db, Request) == 0
    assert await count_rows(db, AuditLog, AuditLog.action == "REPORT_CREATED") == 0


async def test_unknown_problem_type(client: AsyncClient, db: AsyncSession) -> None:
    """TC-API-05: невідомий тип проблеми - 422, маршрутизація не виконується (DQ-02)."""
    response = await create_report(client, db, "flood", ZONES["west"][0])
    assert response.status_code == 422
    assert await count_rows(db, Request) == 0


# ---------- статуси: допустимі переходи ----------


@pytest.mark.parametrize(("current", "target"), list(ALLOWED), ids=lambda v: v)
async def test_allowed_transition(
    client: AsyncClient, db: AsyncSession, current: str, target: str
) -> None:
    """TC-API-06: кожен допустимий перехід - 200, запис в історії та в журналі аудиту."""
    actors = await Actors.create(db)
    report_id = await report_in_status(client, db, actors, current)
    history_before = await count_rows(db, StatusHistory, StatusHistory.request_id == report_id)
    audit_before = await status_changes(db, report_id)

    role = ALLOWED[(current, target)]
    if role == "contractor":
        await assign_contractor(db, actors, report_id)
    if (current, target) in WORK_ORDER_ONLY:
        # «Виконана» - здача робіт з фото «після» й актом (KAN-121).
        response = await submit_work(client, actors.by_role[role], report_id)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target
    else:
        response = await patch(client, actors.by_role[role], report_id, target)
        assert response.status_code == 200, response.text
        assert (response.json()["previous_status"], response.json()["status"]) == (
            current,
            target,
        )

    request = await fresh(db, report_id)
    assert request.status == target
    assert (request.closed_at is not None) == (target in ("resolved", "rejected"))
    assert (
        await count_rows(db, StatusHistory, StatusHistory.request_id == report_id)
        == history_before + 1
    )
    assert await status_changes(db, report_id) == audit_before + 1


# ---------- статуси: недопустимі переходи ----------


@pytest.mark.parametrize(("current", "target"), INVALID, ids=lambda v: v)
async def test_invalid_transition(
    client: AsyncClient, db: AsyncSession, current: str, target: str
) -> None:
    """TC-API-07: недопустимий перехід - 409, статус, історія й журнал не змінюються."""
    actors = await Actors.create(db)
    report_id = await report_in_status(client, db, actors, current)
    dispatcher = actors.by_role["dispatcher"]
    audit_before = await status_changes(db, report_id)
    timeline_before = (
        await client.get(f"{URL}/{report_id}/history", headers=auth(dispatcher))
    ).json()["items"]

    response = await patch(client, dispatcher, report_id, target)
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "недопустимий" in detail or "вже має статус" in detail

    assert (await fresh(db, report_id)).status == current
    assert await status_changes(db, report_id) == audit_before
    timeline = await client.get(f"{URL}/{report_id}/history", headers=auth(dispatcher))
    assert timeline.json()["items"] == timeline_before


async def test_invalid_transition_lists_options(client: AsyncClient, db: AsyncSession) -> None:
    """TC-API-08: повідомлення про помилку підказує, куди можна перейти."""
    actors = await Actors.create(db)
    report_id = await report_in_status(client, db, actors, "new")
    response = await patch(client, actors.by_role["dispatcher"], report_id, "resolved")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Перехід «Нова» → «Усунена» недопустимий. Можливі переходи: «Прийнята», «Відхилена»"
    )


# ---------- статуси: перехід існує, але не для цієї ролі ----------


@pytest.mark.parametrize(
    ("current", "target", "role"),
    [
        ("in_progress", "done", "dispatcher"),
        ("accepted", "rejected", "contractor"),
        ("in_progress", "resolved", "contractor"),
    ],
    ids=["dispatcher-done", "contractor-reject", "contractor-resolve"],
)
async def test_transition_wrong_role(
    client: AsyncClient, db: AsyncSession, current: str, target: str, role: str
) -> None:
    """TC-API-09: перехід допустимий, але не для цієї ролі - 403 і ACCESS_DENIED (БП-6)."""
    actors = await Actors.create(db)
    report_id = await report_in_status(client, db, actors, current)
    if role == "contractor":  # підрядник має бути призначений, інакше відмова за scope
        await assign_contractor(db, actors, report_id)

    response = await patch(client, actors.by_role[role], report_id, target)
    assert response.status_code == 403
    assert (await fresh(db, report_id)).status == current

    denied = await db.scalar(select(AuditLog).where(AuditLog.action == "ACCESS_DENIED"))
    assert denied.entity_id == report_id
    assert denied.new_value["reason"] == f"transition:{current}->{target}"


async def test_done_only_by_work_submission(client: AsyncClient, db: AsyncSession) -> None:
    """TC-API-11 (KAN-121): «Виконана» через PATCH - 409 з підказкою; лише здача робіт з актом."""
    actors = await Actors.create(db)
    report_id = await report_in_status(client, db, actors, "in_progress")
    contractor = actors.by_role["contractor"]
    await assign_contractor(db, actors, report_id)
    audit_before = await status_changes(db, report_id)

    response = await patch(client, contractor, report_id, "done")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Статус «Виконана» ставиться під час здачі робіт: вкажіть прогрес 100 % "
        "і додайте фото «після» та акт виконаних робіт"
    )
    assert (await fresh(db, report_id)).status == "in_progress"
    assert await status_changes(db, report_id) == audit_before

    card = await client.get(f"{URL}/{report_id}", headers=auth(contractor))
    assert "done" not in card.json()["next_statuses"]


async def test_resolve_before_contractor_done(client: AsyncClient, db: AsyncSession) -> None:
    """TC-API-10: роботи веде підрядник - служба не ставить «Усунена» до його «Виконана»."""
    actors = await Actors.create(db)
    report_id = await report_in_status(client, db, actors, "accepted")
    await assign_contractor(db, actors, report_id)
    assert (await patch(client, actors.by_role["contractor"], report_id, "in_progress")).is_success

    response = await patch(client, actors.by_role["dispatcher"], report_id, "resolved")
    assert response.status_code == 409
    assert "Виконана" in response.json()["detail"]
    assert (await fresh(db, report_id)).status == "in_progress"
