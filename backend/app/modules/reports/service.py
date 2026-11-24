"""Бізнес-логіка заявок: створення заявки водієм (UC-01, KAN-57) і зміна статусу
(UC-02, UC-04, KAN-59).

Перевірки йдуть у порядку з п. 3.6: спершу схема Pydantic (типи, межі значень,
довжина коментаря), далі правила, яким потрібна БД (тип з довідника, межі міста),
а обмеження таблиць - остання лінія захисту.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.access_control import AccessContext, deny
from app.core.classification import ROLE_LEVELS
from app.core.enums import ConsentType, DataLevel, PhotoKind, RequestStatus
from app.core.storage import get_storage
from app.modules.admin import repository as reference
from app.modules.audit import service as audit
from app.modules.reports import lifecycle
from app.modules.reports import repository as repo
from app.modules.reports.models import Photo, Request
from app.modules.reports.photos import MAX_PHOTOS, CleanPhoto, PhotoError, clean_photo
from app.modules.reports.schemas import (
    ReportCreatedOut,
    ReportCreateForm,
    ReportHistoryOut,
    StatusChangeIn,
    StatusChangeOut,
    StatusHistoryItem,
)
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


# ---------- зміна статусу (KAN-59) ----------

# Строк можна вказати, коли служба бере заявку в роботу (UC-02, крок 4).
DEADLINE_STATUSES = frozenset({RequestStatus.ACCEPTED, RequestStatus.IN_PROGRESS})


def _check_status_fields(data: StatusChangeIn) -> None:
    """БП-3: відхилити без причини неможливо; причина й строк - лише там, де вони мають сенс."""
    if data.status == RequestStatus.REJECTED and not data.reject_reason:
        raise field_error("reject_reason", "Вкажіть причину відхилення")
    if data.status != RequestStatus.REJECTED and data.reject_reason:
        raise field_error("reject_reason", "Причину вказують лише для відхилення заявки")
    if data.deadline is not None:
        if data.status not in DEADLINE_STATUSES:
            raise field_error(
                "deadline", "Строк вказують, коли заявку приймають або беруть у роботу"
            )
        if data.deadline < datetime.now(UTC).date():
            raise field_error("deadline", "Строк не може бути в минулому")


def _history_comment(data: StatusChangeIn) -> str | None:
    """Що побачить водій у таймлайні: причину відхилення та/або коментар служби."""
    parts = [p for p in (data.reject_reason, data.comment) if p]
    return ". ".join(parts) or None


async def change_status(
    session: AsyncSession, ctx: AccessContext, request_id: int, data: StatusChangeIn
) -> StatusChangeOut:
    """Змінює статус заявки, пише запис у StatusHistory і AuditLog в одній транзакції.

    Порядок перевірок: заявка існує (404) -> заявка в області дії ролі (403) ->
    перехід допустимий (409) -> роль може зробити цей перехід (403, БП-6) ->
    перехід робиться через PATCH, а не здачею робіт (409, KAN-121) -> поля запиту (422).
    """
    request = await repo.get_for_update(session, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявку не знайдено")

    # Статус змінюють основна служба і служба-копія: наприклад, перешкоду поліція
    # фіксує, а комунальна служба прибирає й сама ставить «Усунена».
    # Підрядник - лише в призначеній йому заявці.
    await ctx.ensure_target(
        entity_id=request.id,
        service_ids=[request.service_id, request.copy_service_id],
        contractor_id=request.contractor_id,
    )

    current, target = request.status, data.status
    check = lifecycle.check_transition(current, target, ctx.role)
    if not check.allowed_status:
        raise HTTPException(status.HTTP_409_CONFLICT, check.message)
    if not check.allowed_role:
        exc = await deny(
            ctx.user,
            ctx.role,
            ctx.resource,
            ctx.action,
            ctx.endpoint,
            reason=f"transition:{current.value}->{target.value}",
            entity_id=request.id,
        )
        exc.detail = check.message
        raise exc
    # «Виконана» - лише під час здачі робіт з фото «після» й актом (DQ-08, БП-6):
    # PATCH не має обходити цю перевірку (KAN-121).
    hint = lifecycle.WORK_ORDER_ONLY.get((current, target))
    if hint is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, hint)
    # Якщо роботи виконує підрядник, «Усунена» ставиться лише після його
    # «Виконана» з фотозвітом (UC-04, БП-6).
    if (
        current == RequestStatus.IN_PROGRESS
        and target == RequestStatus.RESOLVED
        and request.contractor_id is not None
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Роботи виконує підрядник: спершу він ставить статус «Виконана»",
        )
    _check_status_fields(data)

    request.status = target
    if target == RequestStatus.REJECTED:
        request.reject_reason = data.reject_reason
    if data.deadline is not None:
        request.deadline = data.deadline
    if target in lifecycle.FINAL_STATUSES:
        request.closed_at = datetime.now(UTC)

    entry = await repo.add_status(
        session, request, current, target, ctx.user.id, _history_comment(data)
    )
    audit.record(
        session,
        "STATUS_CHANGED",
        actor_id=ctx.user.id,
        actor_role=ctx.role.value,
        entity_type="request",
        entity_id=request.id,
        old_value={"status": current.value},
        new_value={
            "status": target.value,
            "number": request.number,
            "reject_reason": data.reject_reason,
            "deadline": data.deadline.isoformat() if data.deadline else None,
            "has_comment": data.comment is not None,
        },
    )
    await session.commit()

    # Подія для сповіщень (KAN-61). Публікується після commit: якщо сповіщення
    # не вдасться надіслати, зміна статусу все одно збережена.
    await events.publish(
        events.StatusChanged(
            request_id=request.id,
            number=request.number,
            author_id=request.author_id,
            from_status=current,
            to_status=target,
            changed_by=ctx.user.id,
            service_id=request.service_id,
            comment=_history_comment(data),
            deadline=request.deadline,
        )
    )

    return StatusChangeOut(
        id=request.id,
        number=request.number,
        previous_status=current,
        status=target,
        reject_reason=request.reject_reason,
        deadline=request.deadline,
        closed_at=request.closed_at,
        changed_at=entry.changed_at,
        next_statuses=lifecycle.next_statuses(target, ctx.role),
    )


async def report_history(
    session: AsyncSession, ctx: AccessContext, request_id: int
) -> ReportHistoryOut:
    """Таймлайн статусів заявки. Водій бачить лише свої заявки, служба - заявки своєї
    служби (зокрема копії), підрядник - призначені йому, адміністратор - усі."""
    request = await repo.get_request(session, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявку не знайдено")
    await ctx.ensure_target(
        entity_id=request.id,
        owner_id=request.author_id,
        service_ids=[request.service_id, request.copy_service_id],
        contractor_id=request.contractor_id,
    )

    # StatusHistory.changed_by - внутрішні дані (табл. 11): водієві не віддаємо.
    show_actor = DataLevel.INTERNAL in ROLE_LEVELS.get(ctx.role, frozenset())
    items = [
        StatusHistoryItem(
            from_status=row.from_status,
            to_status=row.to_status,
            to_label=lifecycle.STATUS_LABELS[row.to_status],
            comment=row.comment,
            changed_at=row.changed_at,
            changed_by=row.changed_by if show_actor else None,
        )
        for row in await repo.list_history(session, request.id)
    ]
    return ReportHistoryOut(
        id=request.id, number=request.number, status=request.status, items=items
    )
