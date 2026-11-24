"""Список підрядників для призначення (UC-04, F-19)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import auth, make_contractor, make_driver, make_staff

URL = "/api/v1/admin/contractors"


async def test_admin_lists_active_contractors(client: AsyncClient, db: AsyncSession) -> None:
    contractor = await make_contractor(db, "ТОВ «Тест Шляхбуд»")
    admin = await make_staff(db, "admin")

    response = await client.get(URL, headers=auth(admin))

    assert response.status_code == 200
    items = response.json()
    assert {"id": contractor.contractor_id, "name": "ТОВ «Тест Шляхбуд»"} in items
    # Конфіденційні дані підрядника (ЄДРПОУ, контакти) не віддаються
    assert all(set(item) == {"id", "name"} for item in items)


async def test_contractors_forbidden_for_other_roles(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    contractor = await make_contractor(db)

    assert (await client.get(URL, headers=auth(driver))).status_code == 403
    assert (await client.get(URL, headers=auth(contractor))).status_code == 403
    assert (await client.get(URL)).status_code == 401
