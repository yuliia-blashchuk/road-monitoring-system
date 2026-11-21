"""Створення заявки (KAN-57, UC-01, DQ-01–DQ-05, DQ-09)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ServiceKind
from app.modules.reports.models import Request, StatusHistory
from tests.factories import KYIV, LVIV, auth, make_driver, make_staff

URL = "/api/v1/reports"


def form(**override) -> dict:
    return {"problem_type": "pothole", **LVIV, **override}


async def count_requests(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(Request))


async def test_driver_creates_report(client: AsyncClient, db: AsyncSession) -> None:
    """TC-UC01-02: заявка без фото й коментаря створюється зі статусом «Нова»."""
    driver = await make_driver(db)
    response = await client.post(URL, data=form(problem_type="obstacle"), headers=auth(driver))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "new"
    assert body["number"] >= 1001
    assert body["problem_type"] == "obstacle"

    request = await db.get(Request, body["id"])
    assert request.author_id == driver.id


async def test_comment_and_address_saved(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    response = await client.post(
        URL,
        data=form(comment="  Глибока яма в правому ряду  ", address="вул. Городоцька, 10"),
        headers=auth(driver),
    )
    request = await db.get(Request, response.json()["id"])
    assert request.comment == "Глибока яма в правому ряду"
    assert request.address == "вул. Городоцька, 10"


async def test_first_status_history_record(client: AsyncClient, db: AsyncSession) -> None:
    """Заявка і перший запис історії зберігаються в одній транзакції."""
    driver = await make_driver(db)
    report_id = (await client.post(URL, data=form(), headers=auth(driver))).json()["id"]
    history = (await db.scalars(select(StatusHistory))).all()
    assert len(history) == 1
    assert history[0].request_id == report_id
    assert history[0].from_status is None and history[0].to_status == "new"
    assert history[0].changed_by == driver.id


async def test_html_comment_stored_as_text(client: AsyncClient, db: AsyncSession) -> None:
    """DQ-05: розмітка зберігається як текст і не обробляється сервером."""
    driver = await make_driver(db)
    response = await client.post(URL, data=form(comment="<b>тег</b>"), headers=auth(driver))
    assert (await db.get(Request, response.json()["id"])).comment == "<b>тег</b>"


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"problem_type": None}, "problem_type"),  # TC-UC01-03, DQ-01
        ({"latitude": 95}, "latitude"),  # DQ-03
        ({"longitude": -200}, "longitude"),
        ({"comment": "я" * 301}, "comment"),  # TC-UC01-07, DQ-05
    ],
)
async def test_schema_validation_422(
    client: AsyncClient, db: AsyncSession, override: dict, field: str
) -> None:
    driver = await make_driver(db)
    data = {k: v for k, v in form(**override).items() if v is not None}
    response = await client.post(URL, data=data, headers=auth(driver))
    assert response.status_code == 422
    assert field in str(response.json()["detail"])
    assert await count_requests(db) == 0


async def test_comment_300_is_ok(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    response = await client.post(URL, data=form(comment="я" * 300), headers=auth(driver))
    assert response.status_code == 201


async def test_unknown_problem_type(client: AsyncClient, db: AsyncSession) -> None:
    """DQ-02: тип має бути з довідника."""
    driver = await make_driver(db)
    response = await client.post(URL, data=form(problem_type="ufo"), headers=auth(driver))
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Невідомий тип проблеми"


async def test_point_outside_city(client: AsyncClient, db: AsyncSession) -> None:
    """TC-UC01-04, виняток E2: точка поза містом - заявку не створено."""
    driver = await make_driver(db)
    response = await client.post(URL, data=form(**KYIV), headers=auth(driver))
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Ділянка не обслуговується"
    assert await count_requests(db) == 0


@pytest.mark.parametrize(
    ("shift", "ok"),
    [
        (timedelta(hours=-2), True),  # офлайн-заявка двогодинної давнини
        (timedelta(hours=-25), False),  # старша за 24 год (DQ-09)
        (timedelta(hours=1), False),  # у майбутньому
    ],
)
async def test_offline_device_time(
    client: AsyncClient, db: AsyncSession, shift: timedelta, ok: bool
) -> None:
    driver = await make_driver(db)
    created = (datetime.now(UTC) + shift).isoformat()
    response = await client.post(URL, data=form(device_created_at=created), headers=auth(driver))
    assert response.status_code == (201 if ok else 422), response.text


async def test_only_driver_can_create(client: AsyncClient, db: AsyncSession) -> None:
    dispatcher = await make_staff(db, "dispatcher", ServiceKind.COMMUNAL)
    response = await client.post(URL, data=form(), headers=auth(dispatcher))
    assert response.status_code == 403


async def test_anonymous_cannot_create(client: AsyncClient) -> None:
    assert (await client.post(URL, data=form())).status_code == 401
