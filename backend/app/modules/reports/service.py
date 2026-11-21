"""Бізнес-логіка заявок: створення заявки водієм (UC-01, KAN-57).

Перевірки йдуть у порядку з п. 3.6: спершу схема Pydantic (типи, межі значень,
довжина коментаря), далі правила, яким потрібна БД (тип з довідника, межі міста),
а обмеження таблиць - остання лінія захисту.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ConsentType, PhotoKind
from app.core.storage import get_storage
from app.modules.admin import repository as reference
from app.modules.audit import service as audit
from app.modules.reports import repository as repo
from app.modules.reports.models import Photo, Request
from app.modules.reports.photos import MAX_PHOTOS, CleanPhoto, PhotoError, clean_photo
from app.modules.reports.schemas import ReportCreatedOut, ReportCreateForm
from app.modules.routing.service import route
from app.modules.users import service as users
from app.modules.users.models import User

HOURLY_LIMIT = 10  # E3, DQ-11: захист від спаму
OFFLINE_MAX_AGE = timedelta(hours=24)  # QR-06, DQ-09
CLOCK_SKEW = timedelta(minutes=5)  # годинник телефона може трохи поспішати


def field_error(field: str, message: str, code: int = status.HTTP_422_UNPROCESSABLE_CONTENT):
    """Помилка у форматі FastAPI: фронтенд підсвічує поле з назвою field."""
    return HTTPException(code, detail=[{"loc": ["body", field], "msg": message}])


def _check_device_time(value: datetime | None) -> None:
    if value is None:
        return
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if value > now + CLOCK_SKEW:
        raise field_error("device_created_at", "Час створення заявки не може бути в майбутньому")
    if value < now - OFFLINE_MAX_AGE:
        raise field_error(
            "device_created_at",
            "Заявка створена понад 24 год тому - підтвердіть, що проблема ще існує",
        )


async def _check_hourly_limit(session: AsyncSession, user: User) -> None:
    since = datetime.now(UTC) - timedelta(hours=1)
    if await repo.count_since(session, user.id, since) >= HOURLY_LIMIT:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Перевищено ліміт: не більше 10 заявок на годину",
        )


def _clean_photos(files: list[tuple[str, bytes]]) -> list[CleanPhoto]:
    if len(files) > MAX_PHOTOS:
        raise field_error("photos", "Можна додати не більше 3 фото")
    try:
        return [clean_photo(name, raw) for name, raw in files]
    except PhotoError as exc:
        raise field_error("photos", str(exc)) from exc


async def _check_consents(
    session: AsyncSession, user: User, data: ReportCreateForm, has_media: bool
) -> None:
    """Перевірка згод перед створенням (п. 3.5): personal_data - завжди,
    media_sharing - якщо водій передає фото або коментар."""
    if not await users.has_consent(session, user, ConsentType.PERSONAL_DATA):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Потрібно прийняти актуальну згоду на обробку персональних даних",
        )
    if not has_media or await users.has_consent(session, user, ConsentType.MEDIA_SHARING):
        return
    if not data.media_sharing_consent:
        raise field_error(
            "media_sharing_consent",
            "Щоб передати службі фото й коментар, потрібна згода на передачу даних",
        )
    await users.grant_consent(session, user, ConsentType.MEDIA_SHARING)


async def create_report(
    session: AsyncSession,
    user: User,
    data: ReportCreateForm,
    files: list[tuple[str, bytes]] | None = None,
) -> ReportCreatedOut:
    files = files or []
    await _check_consents(session, user, data, has_media=bool(files or data.comment))
    await _check_hourly_limit(session, user)
    photos = _clean_photos(files)

    problem_type = await reference.problem_type_by_code(session, data.problem_type)
    if problem_type is None or not problem_type.is_active:
        raise field_error("problem_type", "Невідомий тип проблеми")  # DQ-02

    if not await reference.point_in_city(session, data.latitude, data.longitude):
        raise field_error("location", "Ділянка не обслуговується")  # DQ-03, E2

    _check_device_time(data.device_created_at)

    # Служба, копія і початковий пріоритет за правилами маршрутизації (KAN-58).
    routing = await route(session, problem_type.id, data.latitude, data.longitude)

    request = await repo.add_request(
        session,
        Request(
            author_id=user.id,
            problem_type_id=problem_type.id,
            service_id=routing.service.id if routing.service else None,
            copy_service_id=routing.copy_service.id if routing.copy_service else None,
            priority=routing.priority,
            location=repo.point(data.latitude, data.longitude),
            address=data.address,
            comment=data.comment,
            device_created_at=data.device_created_at,
        ),
    )
    await repo.add_first_status(session, request, user.id)

    # Файли записуються до commit; якщо збереження в БД не вдасться - їх видаляємо,
    # щоб не лишилось фото без заявки (або все, або нічого).
    storage = get_storage()
    saved: list[str] = []
    try:
        for photo in photos:
            key = f"reports/{request.id}/{uuid.uuid4().hex}.{photo.extension}"
            storage.save(key, photo.data)
            saved.append(key)
            session.add(
                Photo(
                    request_id=request.id,
                    uploaded_by=user.id,
                    kind=PhotoKind.BEFORE,
                    storage_key=key,
                    mime_type=photo.mime_type,
                    size_bytes=len(photo.data),
                )
            )
        audit.record(
            session,
            "REPORT_CREATED",
            actor_id=user.id,
            actor_role=user.role.code,
            entity_type="request",
            entity_id=request.id,
            new_value={
                "number": request.number,
                "problem_type": problem_type.code,
                "photos": len(photos),
                "channel": "offline" if data.device_created_at else "online",
                "service_id": routing.service.id if routing.service else None,
                "copy_service_id": routing.copy_service.id if routing.copy_service else None,
                "priority": routing.priority.value,
                "routing_rule_id": routing.rule_id,
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
        for key in saved:
            storage.delete(key)
        raise

    return ReportCreatedOut(
        id=request.id,
        number=request.number,
        status=request.status,
        priority=request.priority,
        problem_type=problem_type.code,
        service=routing.service.name if routing.service else None,
        copy_service=routing.copy_service.name if routing.copy_service else None,
        photos_count=len(photos),
        created_at=request.created_at,
    )
