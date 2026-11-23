"""Читання заявок: публічна карта, «Мої звернення», картка, черга служби, фото.

Права перевіряються так само, як для зміни статусу: спершу політика ролі (require),
потім область дії (ensure_target), а поля картки фільтруються за класифікацією
даних (core/classification.py, табл. 11 і 13).
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import AccessContext, get_policy
from app.core.classification import REQUEST_FIELDS, author_pseudonym, filter_request
from app.core.enums import AccessRole, AccessScope, RequestStatus
from app.core.storage import get_storage
from app.modules.audit import service as audit
from app.modules.reports import lifecycle
from app.modules.reports import read_repository as repo
from app.modules.reports.read_schemas import (
    MapReport,
    MyReport,
    MyReportsPage,
    PhotoInfo,
    QueueItem,
    QueuePage,
    ReportCard,
)

# БП-4: усунені й відхилені заявки з карти прибираються.
MAP_STATUSES = (
    RequestStatus.NEW,
    RequestStatus.ACCEPTED,
    RequestStatus.IN_PROGRESS,
    RequestStatus.DONE,
)
# У черзі служби - незакриті заявки.
QUEUE_STATUSES = MAP_STATUSES


def field_error(field: str, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, detail=[{"loc": ["query", field], "msg": message}]
    )


def parse_bbox(value: str | None) -> repo.BBox | None:
    """bbox=мін_довгота,мін_широта,макс_довгота,макс_широта (як у Leaflet getBounds)."""
    if not value:
        return None
    try:
        min_lng, min_lat, max_lng, max_lat = (float(part) for part in value.split(","))
    except ValueError as exc:
        raise field_error(
            "bbox", "Формат: мін_довгота,мін_широта,макс_довгота,макс_широта"
        ) from exc
    if not (-180 <= min_lng < max_lng <= 180 and -90 <= min_lat < max_lat <= 90):
        raise field_error("bbox", "Межі карти задано неправильно")
    return repo.BBox(min_lng, min_lat, max_lng, max_lat)


def _map_fields(row: repo.ReportRow) -> dict:
    """Публічні поля - однакові для карти, списку, картки й черги."""
    request = row.request
    return {
        "id": request.id,
        "number": request.number,
        "problem_type": row.problem_code,
        "problem_label": row.problem_name,
        "icon": row.icon,
        "color": row.color,
        "status": request.status,
        "status_label": lifecycle.STATUS_LABELS[request.status],
        "lat": row.lat,
        "lng": row.lng,
        "address": request.address,
        "confirmations_count": request.confirmations_count,
        "created_at": request.created_at,
    }


# ---------- публічна карта ----------


async def map_reports(
    session: AsyncSession,
    statuses: list[RequestStatus] | None,
    types: list[str] | None,
    bbox: str | None,
    limit: int,
) -> list[MapReport]:
    if statuses:
        closed = [s for s in statuses if s not in MAP_STATUSES]
        if closed:
            raise field_error("status", "Усунені й відхилені заявки на карті не показуються (БП-4)")
    rows = await repo.map_reports(session, statuses or MAP_STATUSES, types, parse_bbox(bbox), limit)
    return [MapReport(**_map_fields(row)) for row in rows]


# ---------- «Мої звернення» водія ----------


async def my_reports(
    session: AsyncSession, ctx: AccessContext, limit: int, offset: int
) -> MyReportsPage:
    rows, total = await repo.my_reports(session, ctx.user.id, limit, offset)
    counts = await repo.photo_counts(session, [row.request.id for row in rows])
    items = [
        MyReport(
            **_map_fields(row),
            comment=row.request.comment,
            service=row.service_name,
            photos_count=counts.get(row.request.id, 0),
            updated_at=row.request.updated_at,
        )
        for row in rows
    ]
    return MyReportsPage(total=total, limit=limit, offset=offset, items=items)


# ---------- картка заявки ----------

# Поля Request, що потрапляють у картку, якщо їх дозволяє класифікація.
CARD_FIELDS = (
    "comment",
    "priority",
    "deadline",
    "progress_percent",
    "reject_reason",
    "is_suspicious",
    "is_reopened",
    "contractor_id",
)


async def report_card(session: AsyncSession, ctx: AccessContext, request_id: int) -> ReportCard:
    row = await repo.get_row(session, request_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявку не знайдено")
    request = row.request
    await ctx.ensure_target(
        entity_id=request.id,
        owner_id=request.author_id,
        service_ids=[request.service_id, request.copy_service_id],
        contractor_id=request.contractor_id,
    )

    # Другий рівень RBAC: лишаємо поля, дозволені ролі (водій - без внутрішніх полів
    # служби, підрядник - без автора й коментаря, служба - автор лише псевдонімом).
    raw = {key: getattr(request, key) for key in REQUEST_FIELDS if key != "location"}
    allowed = filter_request(raw, ctx.role)

    fields = {**_map_fields(row), "service": row.service_name}
    fields.update({key: allowed[key] for key in CARD_FIELDS if key in allowed})
    if "copy_service_id" in allowed:
        fields["copy_service"] = row.copy_service_name
    if ctx.role != AccessRole.DRIVER:
        for key in ("author", "author_id"):
            if key in allowed:
                fields[key] = allowed[key]

    # Фото - лише ролям із політикою photo.view_original (табл. 14).
    photo_items: list[PhotoInfo] = []
    if await get_policy(session, ctx.role, "photo", "view_original"):
        photo_items = [
            PhotoInfo(
                id=photo.id,
                kind=photo.kind,
                mime_type=photo.mime_type,
                created_at=photo.created_at,
                url=f"/api/v1/reports/{request.id}/photos/{photo.id}",
            )
            for photo in await repo.photos(session, request.id)
        ]
    return ReportCard(
        **fields,
        photos=photo_items,
        next_statuses=lifecycle.next_statuses(request.status, ctx.role),
    )


# ---------- файл фото ----------


async def photo_file(
    session: AsyncSession, ctx: AccessContext, request_id: int, photo_id: int
) -> tuple[bytes, str]:
    row = await repo.get_row(session, request_id)
    photo = await repo.get_photo(session, request_id, photo_id) if row else None
    if row is None or photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Фото не знайдено")
    request = row.request
    await ctx.ensure_target(
        entity_id=request.id,
        owner_id=request.author_id,
        service_ids=[request.service_id, request.copy_service_id],
        contractor_id=request.contractor_id,
    )
    storage = get_storage()
    if not storage.exists(photo.storage_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл фото відсутній у сховищі")
    if ctx.log_access:
        # Оригінал фото - персональні дані: перегляд адміністратором журналюється (табл. 14).
        audit.record(
            session,
            "PHOTO_VIEWED",
            actor_id=ctx.user.id,
            actor_role=ctx.role.value,
            entity_type="request",
            entity_id=request.id,
            new_value={"photo_id": photo.id, "kind": photo.kind.value},
        )
        await session.commit()
    return storage.read(photo.storage_key), photo.mime_type


# ---------- черга служби ----------


async def service_queue(
    session: AsyncSession,
    ctx: AccessContext,
    statuses: list[RequestStatus] | None,
    limit: int,
    offset: int,
) -> QueuePage:
    """Служба бачить заявки, де вона основна або копія; підрядник - призначені йому;
    адміністратор - усі, зокрема без служби (правило не знайдено, DQ-12)."""
    scope = {
        AccessScope.SERVICE: {"service_id": ctx.user.service_id},
        AccessScope.OWN: {"contractor_id": ctx.user.contractor_id},
        AccessScope.ALL: {"everything": True},
    }.get(ctx.scope, {})
    rows, total = await repo.queue(
        session, statuses or QUEUE_STATUSES, limit=limit, offset=offset, **scope
    )
    hide_personal = ctx.role == AccessRole.CONTRACTOR  # БП-5: без автора й коментаря
    items = [
        QueueItem(
            **_map_fields(row),
            priority=row.request.priority,
            comment=None if hide_personal else row.request.comment,
            author=(
                author_pseudonym(row.request.author_id)
                if row.request.author_id and not hide_personal
                else None
            ),
            service=row.service_name,
            is_copy=(
                ctx.user.service_id is not None
                and row.request.copy_service_id == ctx.user.service_id
                and row.request.service_id != ctx.user.service_id
            ),
            deadline=row.request.deadline,
            progress_percent=row.request.progress_percent,
            is_suspicious=row.request.is_suspicious,
            is_reopened=row.request.is_reopened,
            next_statuses=lifecycle.next_statuses(row.request.status, ctx.role),
        )
        for row in rows
    ]
    return QueuePage(total=total, limit=limit, offset=offset, items=items)