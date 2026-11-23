"""Демо-набір даних (KAN-66): дані повні, узгоджені з правилами системи й знеособлені."""

from collections import Counter

from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ConsentType, RequestStatus
from app.modules.admin.models import CityBoundary, ProblemType
from app.modules.audit.models import AuditLog
from app.modules.reports.models import Confirmation, Request, StatusHistory
from app.modules.routing.service import route
from app.modules.users.models import Consent, Role, User
from app.scripts.seed_demo_data import EVENTS, seed

S = RequestStatus
ALLOWED = {
    (None, S.NEW),
    (S.NEW, S.ACCEPTED),
    (S.NEW, S.REJECTED),
    (S.ACCEPTED, S.IN_PROGRESS),
    (S.IN_PROGRESS, S.DONE),
    (S.IN_PROGRESS, S.RESOLVED),
    (S.DONE, S.RESOLVED),
}


async def count(db: AsyncSession, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def test_seed_creates_all_roles_and_reports(db: AsyncSession) -> None:
    await seed("Demo12345")
    roles = Counter((await db.scalars(select(Role.code).join(User, User.role_id == Role.id))).all())
    assert roles["driver"] == 7 and roles["contractor"] == 2
    assert {"operator", "dispatcher", "admin", "data_governance"} <= set(roles)
    assert await count(db, Request) == len(EVENTS) == 53
    statuses = set((await db.scalars(select(Request.status))).all())
    assert statuses == set(RequestStatus)


async def test_seed_is_idempotent(db: AsyncSession) -> None:
    await seed("Demo12345")
    before = [await count(db, m) for m in (User, Request, StatusHistory, Confirmation)]
    await seed("Demo12345")
    assert [await count(db, m) for m in (User, Request, StatusHistory, Confirmation)] == before


async def test_reports_inside_city_and_routed_by_rules(db: AsyncSession) -> None:
    await seed("Demo12345")
    point = cast(Request.location, Geometry)
    inside = await db.scalar(
        select(func.count())
        .select_from(Request)
        .join(CityBoundary, func.ST_Contains(CityBoundary.geom, point))
    )
    assert inside == len(EVENTS)
    # Служба й копія - як у RoutingService для тієї самої точки (F-10, F-23).
    rows = (
        await db.execute(
            select(
                Request.problem_type_id,
                Request.service_id,
                Request.copy_service_id,
                func.ST_Y(cast(Request.location, Geometry)),
                func.ST_X(cast(Request.location, Geometry)),
            )
        )
    ).all()
    for type_id, service_id, copy_id, lat, lon in rows:
        expected = await route(db, type_id, lat, lon)
        assert service_id == expected.service.id
        assert copy_id == (expected.copy_service.id if expected.copy_service else None)


async def test_status_history_is_consistent(db: AsyncSession) -> None:
    await seed("Demo12345")
    for request in (await db.scalars(select(Request))).all():
        steps = (
            await db.scalars(
                select(StatusHistory)
                .where(StatusHistory.request_id == request.id)
                .order_by(StatusHistory.changed_at, StatusHistory.id)
            )
        ).all()
        assert steps[-1].to_status == request.status
        assert all((s.from_status, s.to_status) in ALLOWED for s in steps)
        if request.status == S.REJECTED:
            assert request.reject_reason and request.closed_at
        if request.status in {S.DONE, S.RESOLVED} and request.contractor_id:
            assert request.progress_percent == 100
        if request.status in {S.NEW, S.ACCEPTED}:
            assert request.contractor_id is None and request.closed_at is None


async def test_done_set_by_contractor_resolved_by_service(db: AsyncSession) -> None:
    """БП-6: «Виконана» ставить підрядник, «Усунена» - служба."""
    await seed("Demo12345")
    rows = (
        await db.execute(
            select(StatusHistory.to_status, Role.code)
            .join(User, User.id == StatusHistory.changed_by)
            .join(Role, Role.id == User.role_id)
            .where(StatusHistory.to_status.in_([S.DONE, S.RESOLVED]))
        )
    ).all()
    assert rows
    assert {code for status, code in rows if status == S.DONE} == {"contractor"}
    assert {code for status, code in rows if status == S.RESOLVED} <= {"dispatcher", "operator"}


async def test_confirmations_match_counter(db: AsyncSession) -> None:
    await seed("Demo12345")
    per_request = dict(
        (
            await db.execute(
                select(Confirmation.request_id, func.count()).group_by(Confirmation.request_id)
            )
        ).all()
    )
    for request in (await db.scalars(select(Request))).all():
        assert request.confirmations_count == per_request.get(request.id, 0)
        query = select(Confirmation.user_id).where(Confirmation.request_id == request.id)
        confirmers = (await db.scalars(query)).all()
        assert request.author_id not in confirmers


async def test_comments_only_with_media_consent(db: AsyncSession) -> None:
    """KAN-65: без згоди media_sharing коментар не зберігається."""
    await seed("Demo12345")
    with_media = set(
        (
            await db.scalars(
                select(Consent.user_id).where(
                    Consent.type == ConsentType.MEDIA_SHARING, Consent.revoked_at.is_(None)
                )
            )
        ).all()
    )
    rows = (await db.execute(select(Request.author_id, Request.comment))).all()
    assert any(comment for _, comment in rows)
    assert all(author in with_media for author, comment in rows if comment)


async def test_demo_data_is_anonymized(db: AsyncSession) -> None:
    await seed("Demo12345")
    users = (await db.scalars(select(User))).all()
    assert all(u.email.endswith("@roadmap.local") for u in users)
    assert all(u.phone is None for u in users)


async def test_audit_log_has_demo_history(db: AsyncSession) -> None:
    await seed("Demo12345")
    actions = Counter((await db.scalars(select(AuditLog.action))).all())
    assert actions["REPORT_CREATED"] == len(EVENTS)
    for action in ("STATUS_CHANGED", "WORK_ASSIGNED", "CONSENT_GRANTED", "ACCESS_DENIED"):
        assert actions[action] > 0, action


async def test_every_problem_type_used_is_active(db: AsyncSession) -> None:
    await seed("Demo12345")
    inactive = await db.scalar(
        select(func.count())
        .select_from(Request)
        .join(ProblemType, ProblemType.id == Request.problem_type_id)
        .where(ProblemType.is_active.is_(False))
    )
    assert inactive == 0
