"""Перевірка згоди в бекенді (KAN-65, п. 3.5, табл. 15)."""

from collections.abc import AsyncIterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.consent import (
    MEDIA,
    REPORT_CONSENTS,
    filter_media,
    filter_media_for_service,
    has_consent,
    require_consent,
)
from app.core.enums import ConsentType
from app.modules.audit.models import AuditLog
from app.modules.users import repository as repo
from app.modules.users.models import Consent, User
from tests.test_rbac import auth, make_user

API = "/api/v1/consents"
REPORT = {
    "number": 1001,
    "status": "new",
    "author": "Заявник #4821",
    "comment": "яма",
    "photos": [1],
}


async def register_driver(
    client: AsyncClient, db: AsyncSession, consents: list[str], email: str = "d@test.ua"
) -> User:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Secret123",
            "full_name": "Тестовий водій",
            "consents": consents,
        },
    )
    assert response.status_code == 201, response.text
    return await repo.get_by_id(db, response.json()["id"])


async def audit_actions(db: AsyncSession) -> list[str]:
    return list((await db.scalars(select(AuditLog.action).order_by(AuditLog.id))).all())


# ---------- require_consent на ендпоінті ----------

mini = FastAPI()


@mini.post("/reports")
async def create_report(
    user: Annotated[User, Depends(require_consent(*REPORT_CONSENTS))],
) -> dict:
    return {"author_id": user.id}


@mini.post("/reports/{report_id}/contact")
async def reveal_contact(
    user: Annotated[User, Depends(require_consent(ConsentType.CONTACT))],
) -> dict:
    return {"ok": True}


@pytest.fixture
async def mini_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=mini), base_url="http://test") as c:
        yield c


async def test_driver_with_consents_can_create_report(
    client: AsyncClient, mini_client: AsyncClient, db: AsyncSession
) -> None:
    driver = await register_driver(client, db, ["terms", "personal_data"])
    response = await mini_client.post("/reports", headers=auth(driver))
    assert response.status_code == 200 and response.json() == {"author_id": driver.id}


async def test_missing_consent_denied_and_audited(
    client: AsyncClient, mini_client: AsyncClient, db: AsyncSession
) -> None:
    driver = await register_driver(client, db, ["terms", "personal_data"])
    response = await mini_client.post("/reports/1/contact", headers=auth(driver))
    assert response.status_code == 403
    assert response.json()["detail"] == {
        "message": "Для цієї дії потрібно дозволити диспетчеру зв'язатися з вами",
        "missing_consents": ["contact"],
    }
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "ACCESS_DENIED"))
    assert entry.actor_id == driver.id and entry.result == "denied"
    assert entry.new_value["reason"] == "consent_missing:contact"


async def test_revoked_required_consent_blocks_reports(
    client: AsyncClient, mini_client: AsyncClient, db: AsyncSession
) -> None:
    driver = await register_driver(client, db, ["terms", "personal_data"])
    await repo.revoke_consent(db, driver.id, ConsentType.PERSONAL_DATA)
    await db.commit()
    response = await mini_client.post("/reports", headers=auth(driver))
    assert response.status_code == 403
    assert response.json()["detail"]["missing_consents"] == ["personal_data"]


async def test_new_consent_version_requires_reaccept(
    client: AsyncClient, mini_client: AsyncClient, db: AsyncSession
) -> None:
    """Змінився текст згоди - нові заявки неможливі, доки водій не прийме нову версію."""
    driver = await register_driver(client, db, ["terms", "personal_data"])
    settings = get_settings()
    old_version = settings.consent_version
    settings.consent_version = "2.0"
    try:
        response = await mini_client.post("/reports", headers=auth(driver))
        assert response.status_code == 403
        assert set(response.json()["detail"]["missing_consents"]) == {"terms", "personal_data"}

        statuses = (await client.get(f"{API}/me", headers=auth(driver))).json()
        assert next(s for s in statuses if s["type"] == "terms")["outdated"] is True

        for t in ("terms", "personal_data"):
            await client.put(f"{API}/me/{t}", headers=auth(driver))
        assert (await mini_client.post("/reports", headers=auth(driver))).status_code == 200
    finally:
        settings.consent_version = old_version


@pytest.mark.parametrize("key", ["dispatcher", "police", "contractor", "admin"])
async def test_staff_not_subject_to_driver_consent(
    mini_client: AsyncClient, db: AsyncSession, key: str
) -> None:
    """Працівники обробляються на іншій підставі (п. 3.5); права перевіряє RBAC."""
    staff = await make_user(db, key)
    assert (await mini_client.post("/reports/1/contact", headers=auth(staff))).status_code == 200


# ---------- фото й коментар без media_sharing ----------


def test_filter_media_without_consent() -> None:
    assert filter_media(REPORT, media_allowed=True) == REPORT
    assert filter_media(REPORT, media_allowed=False) == {
        "number": 1001,
        "status": "new",
        "author": "Заявник #4821",
    }


async def test_service_queue_gets_media_only_with_consent(
    client: AsyncClient, db: AsyncSession
) -> None:
    with_media = await register_driver(client, db, ["terms", "personal_data", "media_sharing"])
    without = await register_driver(client, db, ["terms", "personal_data"], email="n@test.ua")
    queue = await filter_media_for_service(
        db, [REPORT, REPORT, REPORT], [with_media.id, without.id, None]
    )
    assert ["comment" in r for r in queue] == [True, False, False]


async def test_revoked_media_consent_applies_to_next_transfer(
    client: AsyncClient, db: AsyncSession
) -> None:
    driver = await register_driver(client, db, ["terms", "personal_data", "media_sharing"])
    assert await has_consent(db, driver.id, MEDIA)
    await client.delete(f"{API}/me/media_sharing", headers=auth(driver))
    assert not await has_consent(db, driver.id, MEDIA)
    [view] = await filter_media_for_service(db, [REPORT], [driver.id])
    assert "photos" not in view and "comment" not in view


# ---------- «Мої згоди» ----------


async def test_my_consents_lists_all_types(client: AsyncClient, db: AsyncSession) -> None:
    driver = await register_driver(client, db, ["terms", "personal_data"])
    response = await client.get(f"{API}/me", headers=auth(driver))
    assert response.status_code == 200
    by_type = {s["type"]: s for s in response.json()}
    assert set(by_type) == {t.value for t in ConsentType}
    assert by_type["terms"]["required"] and by_type["terms"]["active"]
    assert not by_type["contact"]["required"] and not by_type["contact"]["active"]


async def test_grant_is_idempotent_and_audited(client: AsyncClient, db: AsyncSession) -> None:
    driver = await register_driver(client, db, ["terms", "personal_data"])
    for _ in range(2):
        response = await client.put(f"{API}/me/contact", headers=auth(driver))
        assert response.status_code == 200
    records = (
        await db.scalars(
            select(Consent).where(Consent.user_id == driver.id, Consent.type == "contact")
        )
    ).all()
    assert len(records) == 1
    assert (await audit_actions(db)).count("CONSENT_GRANTED") == 3  # 2 при реєстрації + 1


async def test_revoke_keeps_history(client: AsyncClient, db: AsyncSession) -> None:
    """Запис не видаляється: відкликання лише заповнює revoked_at."""
    driver = await register_driver(client, db, ["terms", "personal_data", "contact"])
    response = await client.delete(f"{API}/me/contact", headers=auth(driver))
    assert response.status_code == 200
    contact = next(s for s in response.json() if s["type"] == "contact")
    assert contact["active"] is False and contact["revoked_at"] is not None
    record = await db.scalar(
        select(Consent).where(Consent.type == "contact").execution_options(populate_existing=True)
    )
    assert record is not None and record.revoked_at is not None
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "CONSENT_REVOKED"))
    assert entry.old_value == {"type": "contact", "version": record.version}


async def test_revoke_again_writes_nothing(client: AsyncClient, db: AsyncSession) -> None:
    driver = await register_driver(client, db, ["terms", "personal_data"])
    assert (await client.delete(f"{API}/me/contact", headers=auth(driver))).status_code == 200
    assert "CONSENT_REVOKED" not in await audit_actions(db)


@pytest.mark.parametrize("consent_type", ["terms", "personal_data"])
async def test_required_consent_cannot_be_revoked(
    client: AsyncClient, db: AsyncSession, consent_type: str
) -> None:
    driver = await register_driver(client, db, ["terms", "personal_data"])
    response = await client.delete(f"{API}/me/{consent_type}", headers=auth(driver))
    assert response.status_code == 409
    assert await has_consent(db, driver.id, ConsentType(consent_type))


@pytest.mark.parametrize("key", ["dispatcher", "contractor", "admin", "dg"])
async def test_only_driver_manages_own_consents(
    client: AsyncClient, db: AsyncSession, key: str
) -> None:
    user = await make_user(db, key)
    assert (await client.get(f"{API}/me", headers=auth(user))).status_code == 403


async def test_stats_for_data_governance(client: AsyncClient, db: AsyncSession) -> None:
    await register_driver(client, db, ["terms", "personal_data", "contact"])
    second = await register_driver(client, db, ["terms", "personal_data", "contact"], "b@test.ua")
    await client.delete(f"{API}/me/contact", headers=auth(second))

    dg = await make_user(db, "dg")
    response = await client.get(f"{API}/stats", headers=auth(dg))
    assert response.status_code == 200
    stats = {s["type"]: s for s in response.json()}
    assert stats["terms"] == {
        "type": "terms",
        "required": True,
        "active": 2,
        "revoked": 0,
        "outdated": 0,
    }
    assert stats["contact"]["active"] == 1 and stats["contact"]["revoked"] == 1
    assert stats["media_sharing"]["active"] == 0
    # Без персональних даних - лише лічильники.
    fields = {"type", "required", "active", "revoked", "outdated"}
    assert all(set(s) == fields for s in stats.values())


@pytest.mark.parametrize("key", ["driver", "dispatcher", "admin"])
async def test_stats_denied_for_others(client: AsyncClient, db: AsyncSession, key: str) -> None:
    user = await make_user(db, key)
    assert (await client.get(f"{API}/stats", headers=auth(user))).status_code == 403
