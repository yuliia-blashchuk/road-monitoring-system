"""Допоміжні функції тестів: створення користувачів і заголовка з токеном."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ConsentType, ServiceKind
from app.core.security import create_access_token, hash_password
from app.modules.admin.models import Service
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


async def make_staff(db: AsyncSession, role: str, kind: ServiceKind | None = None) -> User:
    service = await db.scalar(select(Service).where(Service.kind == kind)) if kind else None
    user = User(
        email=f"{role}-{kind or 'none'}@test.ua",
        password_hash=hash_password("Secret123"),
        full_name=role,
        role_id=(await repo.get_role(db, role)).id,
        service_id=service.id if service else None,
    )
    await repo.add_user(db, user)
    await db.commit()
    return await repo.get_by_id(db, user.id)


def auth(user: User) -> dict[str, str]:
    token, _ = create_access_token(user.id, user.role.code)
    return {"Authorization": f"Bearer {token}"}
