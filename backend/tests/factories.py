"""Допоміжні функції тестів: створення користувачів і заголовка з токеном."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ConsentType, ServiceKind
from app.core.security import create_access_token, hash_password
from app.modules.admin.models import Contractor, Service
from app.modules.users import repository as repo
from app.modules.users.models import User

LVIV = {"latitude": 49.8397, "longitude": 24.0297}
KYIV = {"latitude": 50.4501, "longitude": 30.5234}


async def make_driver(
    db: AsyncSession,
    email: str = "driver@test.ua",
    consents: tuple[ConsentType, ...] = (
        ConsentType.TERMS,
        ConsentType.PERSONAL_DATA,
        ConsentType.MEDIA_SHARING,
    ),
) -> User:
    user = User(
        email=email,
        password_hash=hash_password("Secret123"),
        full_name="Тест Водій",
        role_id=(await repo.get_role(db, "driver")).id,
    )
    await repo.add_user(db, user)
    await repo.add_consents(db, user, list(consents), get_settings().consent_version)
    await db.commit()
    return await repo.get_by_id(db, user.id)


async def make_staff(
    db: AsyncSession,
    role: str,
    kind: ServiceKind | None = None,
    service_name: str | None = None,
) -> User:
    """Працівник служби. service_name - конкретна служба (інакше перша служба виду kind)."""
    if service_name:
        service = await db.scalar(select(Service).where(Service.name == service_name))
    elif kind:
        service = await db.scalar(select(Service).where(Service.kind == kind))
    else:
        service = None
    user = User(
        email=f"{role}-{service.id if service else 'none'}@test.ua",
        password_hash=hash_password("Secret123"),
        full_name=role,
        role_id=(await repo.get_role(db, role)).id,
        service_id=service.id if service else None,
    )
    await repo.add_user(db, user)
    await db.commit()
    return await repo.get_by_id(db, user.id)


async def make_contractor(db: AsyncSession, name: str = "Тест-підрядник") -> User:
    contractor = Contractor(name=name, edrpou=str(10_000_000 + len(name)))
    db.add(contractor)
    await db.flush()
    user = User(
        email=f"contractor-{contractor.id}@test.ua",
        password_hash=hash_password("Secret123"),
        full_name=name,
        role_id=(await repo.get_role(db, "contractor")).id,
        contractor_id=contractor.id,
    )
    await repo.add_user(db, user)
    await db.commit()
    return await repo.get_by_id(db, user.id)


def auth(user: User) -> dict[str, str]:
    token, _ = create_access_token(user.id, user.role.code)
    return {"Authorization": f"Bearer {token}"}
