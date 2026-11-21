"""Згоди і журнал аудиту під час створення заявки (KAN-57, п. 3.5, табл. 18)."""

from datetime import UTC, datetime, timedelta
from io import BytesIO

from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ConsentType
from app.modules.audit.models import AuditLog
from app.modules.reports.models import Request
from app.modules.users.models import Consent
from tests.factories import LVIV, auth, make_driver

URL = "/api/v1/reports"
FORM = {"problem_type": "pothole", **LVIV}
BASIC = (ConsentType.TERMS, ConsentType.PERSONAL_DATA)  # без media_sharing


def jpeg() -> bytes:
    out = BytesIO()
    Image.new("RGB", (10, 10)).save(out, "JPEG")
    return out.getvalue()


def photo() -> list:
    return [("photos", ("p.jpg", jpeg(), "image/jpeg"))]


async def count(db: AsyncSession, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def test_no_personal_data_consent_403(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db, consents=(ConsentType.TERMS,))
    response = await client.post(URL, data=FORM, headers=auth(driver))
    assert response.status_code == 403
    assert "персональних даних" in response.json()["detail"]


async def test_outdated_consent_version_403(client: AsyncClient, db: AsyncSession) -> None:
    """Нова версія тексту згоди: доки її не прийнято, нових заявок створити не можна."""
    driver = await make_driver(db)
    await db.execute(text("UPDATE consent SET version = '0.9'"))
    await db.commit()
    response = await client.post(URL, data=FORM, headers=auth(driver))
    assert response.status_code == 403


async def test_revoked_consent_403(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    await db.execute(text("UPDATE consent SET revoked_at = now() WHERE type = 'personal_data'"))
    await db.commit()
    assert (await client.post(URL, data=FORM, headers=auth(driver))).status_code == 403


async def test_public_fields_only_without_media_consent(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Без media_sharing можна надіслати тип і точку, але не фото чи коментар."""
    driver = await make_driver(db, consents=BASIC)
    assert (await client.post(URL, data=FORM, headers=auth(driver))).status_code == 201


async def test_photo_without_media_consent_422(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db, consents=BASIC)
    response = await client.post(URL, data=FORM, files=photo(), headers=auth(driver))
    assert response.status_code == 422
    assert "media_sharing_consent" in str(response.json())
    assert await count(db, Request) == 0


async def test_comment_without_media_consent_422(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db, consents=BASIC)
    data = {**FORM, "comment": "Яма біля зупинки"}
    response = await client.post(URL, data=data, headers=auth(driver))
    assert response.status_code == 422


async def test_consent_from_form_is_saved(client: AsyncClient, db: AsyncSession) -> None:
    """Галочка у формі створює запис Consent і подію CONSENT_GRANTED."""
    driver = await make_driver(db, consents=BASIC)
    data = {**FORM, "media_sharing_consent": "true"}
    response = await client.post(URL, data=data, files=photo(), headers=auth(driver))
    assert response.status_code == 201, response.text

    consent = await db.scalar(select(Consent).where(Consent.type == ConsentType.MEDIA_SHARING))
    assert consent.user_id == driver.id
    granted = await db.scalar(select(AuditLog).where(AuditLog.action == "CONSENT_GRANTED"))
    assert granted.entity_id == consent.id


async def test_existing_consent_not_duplicated(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)  # media_sharing уже надано
    data = {**FORM, "media_sharing_consent": "true"}
    await client.post(URL, data=data, files=photo(), headers=auth(driver))
    total = await db.scalar(
        select(func.count()).select_from(Consent).where(Consent.type == ConsentType.MEDIA_SHARING)
    )
    assert total == 1


async def test_report_created_audit(client: AsyncClient, db: AsyncSession) -> None:
    """REPORT_CREATED з номером, типом, кількістю фото і каналом (табл. 18, 19)."""
    driver = await make_driver(db)
    body = (await client.post(URL, data=FORM, files=photo(), headers=auth(driver))).json()

    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "REPORT_CREATED"))
    assert entry.actor_id == driver.id and entry.actor_role == "driver"
    assert entry.entity_type == "request" and entry.entity_id == body["id"]
    assert entry.new_value["number"] == body["number"]
    assert entry.new_value["problem_type"] == "pothole"
    assert entry.new_value["photos"] == 1
    assert entry.new_value["channel"] == "online"
    assert entry.correlation_id is not None


async def test_offline_channel_in_audit(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    data = {**FORM, "device_created_at": "2099-01-01T00:00:00Z"}
    assert (await client.post(URL, data=data, headers=auth(driver))).status_code == 422

    data["device_created_at"] = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    await client.post(URL, data=data, headers=auth(driver))
    entry = await db.scalar(select(AuditLog).where(AuditLog.action == "REPORT_CREATED"))
    assert entry.new_value["channel"] == "offline"


async def test_failed_report_leaves_no_audit(client: AsyncClient, db: AsyncSession) -> None:
    driver = await make_driver(db)
    data = {**FORM, "problem_type": "ufo"}
    await client.post(URL, data=data, headers=auth(driver))
    assert await count(db, AuditLog) == 0
