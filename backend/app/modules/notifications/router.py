"""Стрічка сповіщень поточного користувача (табл. 18: /notifications).

Кожен бачить і змінює лише власні сповіщення, тому окрема політика доступу
не потрібна: достатньо, щоб користувач увійшов у систему.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.modules.notifications import repository as repo
from app.modules.notifications import service  # noqa: F401  - підписка на події
from app.modules.notifications.schemas import NotificationOut, NotificationPage, ReadAllOut
from app.modules.users.dependencies import CurrentUser, SessionDep

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPage, summary="Мої сповіщення")
async def list_notifications(
    session: SessionDep,
    user: CurrentUser,
    unread_only: Annotated[bool, Query(description="Лише непрочитані")] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationPage:
    """Сповіщення від новіших до старіших і кількість непрочитаних. Фронтенд може
    опитувати цю адресу раз на 15-20 с, щоб зміна статусу з'являлася ≤ 30 с (QR-03)."""
    rows, total = await repo.list_for_user(session, user.id, unread_only, limit, offset)
    return NotificationPage(
        total=total,
        unread=await repo.count_unread(session, user.id),
        limit=limit,
        offset=offset,
        items=[NotificationOut.model_validate(row) for row in rows],
    )


@router.post(
    "/{notification_id}/read",
    response_model=NotificationOut,
    summary="Позначити сповіщення прочитаним",
    responses={404: {"description": "Сповіщення не знайдено або воно чуже"}},
)
async def mark_read(
    notification_id: int, session: SessionDep, user: CurrentUser
) -> NotificationOut:
    notification = await repo.get_own(session, notification_id, user.id)
    if notification is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сповіщення не знайдено")
    notification.is_read = True
    await session.commit()
    return NotificationOut.model_validate(notification)


@router.post("/read-all", response_model=ReadAllOut, summary="Позначити всі прочитаними")
async def mark_all_read(session: SessionDep, user: CurrentUser) -> ReadAllOut:
    updated = await repo.mark_all_read(session, user.id)
    await session.commit()
    return ReadAllOut(updated=updated)