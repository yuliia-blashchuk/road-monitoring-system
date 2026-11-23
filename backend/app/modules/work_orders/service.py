"""Бізнес-логіка підрядних робіт (KAN-62; UC-04, UC-06; F-19, F-20; БП-5, БП-6).

Окремої таблиці робіт поки немає: підрядник, строк і прогрес зберігаються в Request
(contractor_id, deadline, progress_percent), фото «після» й акт - у Photo.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_control import AccessContext
from app.core.enums import AccessScope, PhotoKind, RequestStatus
from app.core.storage import get_storage
from app.modules.audit import service as audit
from app.modules.reports import lifecycle
from app.modules.reports import repository as reports_repo
from app.modules.reports.models import MAX_PHOTO_BYTES, Photo, Request
from app.modules.reports.photos import MAX_PHOTOS, CleanPhoto, PhotoError, clean_photo
from app.modules.reports.service import field_error
from app.modules.work_orders import repository as repo
from app.modules.work_orders.schemas import (
    ProgressOut,
    WorkOrderAssignIn,
    WorkOrderOut,
)

# Призначити або змінити підрядника можна, поки роботи не здано (UC-04, A1).
ASSIGNABLE = frozenset({RequestStatus.ACCEPTED, RequestStatus.IN_PROGRESS})
CLOSED = frozenset({RequestStatus.DONE, RequestStatus.RESOLVED, RequestStatus.REJECTED})


def _to_out(row) -> WorkOrderOut:
    request, contractor_name, problem_code = row
    overdue = (
        request.deadline is not None
        and request.deadline < datetime.now(UTC).date()
        and request.status not in CLOSED
    )
    return WorkOrderOut(
        id=request.id,
        number=request.number,
        status=request.status,
        priority=request.priority,
        problem_type=problem_code,
        address=request.address,
        service_id=request.service_id,
        contractor_id=request.contractor_id,
        contractor_name=contractor_name,
        deadline=request.deadline,
        progress_percent=request.progress_percent,
        is_overdue=overdue,
    )


async def assign(
    session: AsyncSession, ctx: AccessContext, data: WorkOrderAssignIn
) -> WorkOrderOut:
    """Адміністратор обирає підрядника зі строком. Якщо підрядника змінюють,
    попередній втрачає доступ до заявки одразу (БП-5)."""
    request = await reports_repo.get_for_update(session, data.request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявку не знайдено")
    if request.status not in ASSIGNABLE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Підрядника призначають на заявку зі статусом «Прийнята» або «В роботі»",
        )
    contractor = await repo.get_contractor(session, data.contractor_id)
    if contractor is None or not contractor.is_active:
        raise field_error("contractor_id", "Підрядника немає в реєстрі або він неактивний")
    if data.deadline < datetime.now(UTC).date():
        raise field_error("deadline", "Строк не може бути в минулому")

    old = {
        "contractor_id": request.contractor_id,
        "deadline": request.deadline.isoformat() if request.deadline else None,
    }
    request.contractor_id = contractor.id
    request.deadline = data.deadline
    audit.record(
        session,
        "WORK_ASSIGNED",
        actor_id=ctx.user.id,
        actor_role=ctx.role.value,
        entity_type="request",
        entity_id=request.id,
        old_value=old,
        new_value={
            "number": request.number,
            "contractor_id": contractor.id,
            "deadline": data.deadline.isoformat(),
            "scope": data.scope,
        },
    )
    await session.commit()
    return _to_out(await repo.get_row(session, request.id))


async def list_orders(
    session: AsyncSession,
    ctx: AccessContext,
    status_filter: RequestStatus | None,
    limit: int,
    offset: int,
) -> list[WorkOrderOut]:
    scope = ctx.scope
    if scope == AccessScope.PUBLIC:  # політика work.view публічною не буває; страховка
        scope = AccessScope.OWN
    rows, _ = await repo.list_rows(session, scope, ctx.user, status_filter, limit, offset)
    return [_to_out(row) for row in rows]


# ---------- прогрес і акт (UC-06) ----------


def _clean_act(file: tuple[str, bytes]) -> CleanPhoto:
    """Акт: PDF або зображення. PDF перевіряємо за сигнатурою, а не за розширенням."""
    name, raw = file
    if raw[:5] == b"%PDF-":
        if len(raw) > MAX_PHOTO_BYTES:
            raise PhotoError(f"{name}: розмір понад 5 МБ")
        return CleanPhoto(mime_type="application/pdf", extension="pdf", data=raw)
    return clean_photo(name, raw)


async def read_upload(file: UploadFile | None) -> tuple[str, bytes] | None:
    if file is None or not file.filename:
        return None
    return file.filename, await file.read(MAX_PHOTO_BYTES + 1)


async def update_progress(
    session: AsyncSession,
    ctx: AccessContext,
    request_id: int,
    percent: int,
    comment: str | None,
    photo_files: list[tuple[str, bytes]],
    act_file: tuple[str, bytes] | None,
) -> ProgressOut:
    request = await reports_repo.get_for_update(session, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявку не знайдено")
    # Підрядник працює лише з призначеною йому заявкою (БП-5, E1): інакше 403 + аудит.
    await ctx.ensure_target(entity_id=request.id, contractor_id=request.contractor_id)

    if request.status != RequestStatus.IN_PROGRESS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Прогрес оновлюють у статусі «В роботі»: спершу поставте «Роботи розпочато»",
        )
    previous = request.progress_percent or 0
    if percent < previous:
        raise field_error("progress_percent", f"Прогрес не може зменшуватись (зараз {previous} %)")
    if len(photo_files) > MAX_PHOTOS:
        raise field_error("photos", f"За один раз можна додати не більше {MAX_PHOTOS} фото")
    try:
        photos = [clean_photo(name, raw) for name, raw in photo_files]
        act = _clean_act(act_file) if act_file else None
    except PhotoError as exc:
        raise field_error("photos" if not act_file else "act", str(exc)) from exc

    submit = percent == 100
    if submit:
        # БП-6: роботи здають із фото «після» й актом виконаних робіт.
        have_after = len(photos) + await repo.count_photos(session, request.id, PhotoKind.AFTER)
        have_act = (1 if act else 0) + await repo.count_photos(session, request.id, PhotoKind.ACT)
        if have_after == 0:
            raise field_error("photos", "При 100 % потрібне фото «після»")
        if have_act == 0:
            raise field_error("act", "При 100 % потрібен акт виконаних робіт")

    storage = get_storage()
    saved: list[str] = []
    try:
        for kind, item in [(PhotoKind.AFTER, p) for p in photos] + (
            [(PhotoKind.ACT, act)] if act else []
        ):
            key = f"reports/{request.id}/{uuid.uuid4().hex}.{item.extension}"
            storage.save(key, item.data)
            saved.append(key)
            session.add(
                Photo(
                    request_id=request.id,
                    uploaded_by=ctx.user.id,
                    kind=kind,
                    storage_key=key,
                    mime_type=item.mime_type,
                    size_bytes=len(item.data),
                )
            )
        request.progress_percent = percent
        audit.record(
            session,
            "WORK_PROGRESS_UPDATED",
            actor_id=ctx.user.id,
            actor_role=ctx.role.value,
            entity_type="request",
            entity_id=request.id,
            old_value={"progress_percent": previous},
            new_value={
                "number": request.number,
                "progress_percent": percent,
                "photos": len(photos),
                "act": act is not None,
                "has_comment": comment is not None,
            },
        )
        if submit:
            _submit(session, request, ctx)
            await reports_repo.add_status(
                session,
                request,
                RequestStatus.IN_PROGRESS,
                RequestStatus.DONE,
                ctx.user.id,
                comment or "Роботи здано: фото «після» й акт завантажено",
            )
            audit.record(
                session,
                "STATUS_CHANGED",
                actor_id=ctx.user.id,
                actor_role=ctx.role.value,
                entity_type="request",
                entity_id=request.id,
                old_value={"status": RequestStatus.IN_PROGRESS.value},
                new_value={"status": RequestStatus.DONE.value, "number": request.number},
            )
        await session.commit()
    except Exception:
        await session.rollback()
        for key in saved:
            storage.delete(key)
        raise

    return ProgressOut(
        id=request.id,
        number=request.number,
        status=request.status,
        progress_percent=percent,
        photos_added=len(photos),
        act_attached=act is not None,
        submitted=submit,
    )


def _submit(session: AsyncSession, request: Request, ctx: AccessContext) -> None:
    """Перехід «В роботі» → «Виконана» за правилами життєвого циклу (лише підрядник)."""
    check = lifecycle.check_transition(request.status, RequestStatus.DONE, ctx.role)
    if not check.ok:
        raise HTTPException(status.HTTP_409_CONFLICT, check.message)
    request.status = RequestStatus.DONE
