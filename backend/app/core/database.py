"""Підключення до БД: двигун SQLAlchemy, сесії, базовий клас моделей."""

from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

# У тестах кожен тест має власний цикл подій, тому пул з'єднань вимикаємо.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    **({"poolclass": NullPool} if settings.environment == "test" else {}),
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Однакові імена індексів і обмежень, щоб міграції були передбачуваними.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Від цього класу наслідуються всі моделі (таблиці) у modules/*/models.py."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """Залежність FastAPI: дає сесію БД на час одного запиту."""
    async with SessionLocal() as session:
        yield session
