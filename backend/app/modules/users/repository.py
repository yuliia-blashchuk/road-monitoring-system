"""Запити до БД модуля users."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ConsentType
from app.modules.users.models import Consent, Role, User


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email.lower()))


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_role(session: AsyncSession, code: str) -> Role:
    return (await session.scalars(select(Role).where(Role.code == code))).one()


async def add_user(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.flush()
    return user


async def add_consents(
    session: AsyncSession, user: User, types: list[ConsentType], version: str
) -> list[Consent]:
    consents = [Consent(user_id=user.id, type=t, version=version) for t in types]
    session.add_all(consents)
    await session.flush()
    return consents


async def active_consents(session: AsyncSession, user_id: int) -> list[Consent]:
    rows = await session.scalars(
        select(Consent)
        .where(Consent.user_id == user_id, Consent.revoked_at.is_(None))
        .order_by(Consent.type)
    )
    return list(rows)


def touch_last_login(user: User) -> None:
    user.last_login_at = datetime.now(UTC)
