"""Бізнес-логіка дедуплікації та «Теж бачу» (F-21, F-22, БП-1, DQ-07).

Правила:
- дублікат - активна заявка того самого типу в радіусі 30 м від нової точки;
- водій підтверджує чужу заявку один раз; свою заявку підтвердити не можна;
- закриту заявку («Усунена», «Відхилена») підтвердити не можна;
- коли підтверджень стає 5, пріоритет піднімається на один рівень (БП-1), один раз.
"""

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Priority
from app.modules.audit import service as audit
from app.modules.dedup import repository as repo
from app.modules.dedup.repository import CLOSED_STATUSES, NearbyRow
from app.modules.users.models import User

DUPLICATE_RADIUS_M = 30
CONFIRMATIONS_TO_RAISE = 5
NEARBY_LIMIT = 5

PRIORITY_ORDER = (Priority.LOW, Priority.MEDIUM, Priority.HIGH, Priority.CRITICAL)


class ConfirmError(Exception):
    """Підтвердження неможливе. code - для HTTP-відповіді в router."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Confirmed:
    request_id: int
    confirmations_count: int
    priority_raised: bool


def raise_priority(priority: Priority) -> Priority:
    """На один рівень вище; критичний лишається критичним."""
    index = PRIORITY_ORDER.index(priority)
    return PRIORITY_ORDER[min(index + 1, len(PRIORITY_ORDER) - 1)]


async def find_duplicates(
    session: AsyncSession,
    *,
    lat: float,
    lng: float,
    problem_type_id: int,
    radius_m: float = DUPLICATE_RADIUS_M,
    limit: int = NEARBY_LIMIT,
) -> list[NearbyRow]:
    """Схожі активні заявки поруч, найближчі першими.

    Викликається з форми (GET /reports/nearby) і з модуля reports перед створенням заявки.
    """
    return await repo.find_nearby(
        session,
        lat=lat,
        lng=lng,
        problem_type_id=problem_type_id,
        radius_m=radius_m,
        limit=limit,
    )


async def confirm(session: AsyncSession, request_id: int, user: User) -> Confirmed:
    """«Теж бачу»: додає підтвердження, збільшує лічильник і за потреби пріоритет."""
    request = await repo.get_request_for_update(session, request_id)
    if request is None:
        raise ConfirmError("not_found", "Заявку не знайдено")
    if request.status in CLOSED_STATUSES:
        raise ConfirmError("closed", "Заявку вже закрито, підтвердити її не можна")
    if request.author_id == user.id:
        raise ConfirmError("own", "Не можна підтвердити власну заявку")
    if await repo.has_confirmation(session, request.id, user.id):
        raise ConfirmError("duplicate", "Ви вже підтвердили цю заявку")

    repo.add_confirmation(session, request.id, user.id)
    old_count = request.confirmations_count
    request.confirmations_count = old_count + 1
    audit.record(
        session,
        "REPORT_CONFIRMED",
        actor_id=user.id,
        actor_role=user.role.code,
        entity_type="request",
        entity_id=request.id,
        old_value={"confirmations_count": old_count},
        new_value={"confirmations_count": request.confirmations_count},
    )

    priority_raised = False
    if request.confirmations_count == CONFIRMATIONS_TO_RAISE:
        old_priority = request.priority
        new_priority = raise_priority(old_priority)
        if new_priority != old_priority:
            request.priority = new_priority
            priority_raised = True
            audit.record(
                session,
                "PRIORITY_RECALCULATED",
                actor_id=None,  # дія системи
                entity_type="request",
                entity_id=request.id,
                old_value={"priority": old_priority.value},
                new_value={
                    "priority": new_priority.value,
                    "reason": f"BP-1: {CONFIRMATIONS_TO_RAISE} confirmations",
                },
            )

    try:
        await session.commit()
    except IntegrityError as exc:
        # Той самий водій натиснув двічі одночасно - спрацювало унікальне обмеження.
        await session.rollback()
        raise ConfirmError("duplicate", "Ви вже підтвердили цю заявку") from exc

    return Confirmed(request.id, request.confirmations_count, priority_raised)
