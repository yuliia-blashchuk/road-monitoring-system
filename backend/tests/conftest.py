"""Спільні налаштування тестів.

Тести працюють з окремою базою <POSTGRES_DB>_test: вона створюється автоматично,
до неї застосовуються всі міграції, а після кожного тесту таблиці з даними
користувачів очищуються (довідники й політики лишаються).
"""

import os

# Налаштування задаємо до імпорту застосунку, щоб він підключився до тестової БД.
os.environ["ENVIRONMENT"] = "test"
_base_db = os.environ.get("POSTGRES_DB", "roadmap")
if not _base_db.endswith("_test"):
    os.environ["POSTGRES_DB"] = f"{_base_db}_test"
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-0123456789")

import asyncio  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from pathlib import Path  # noqa: E402

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Таблиці з даними, що створюються в тестах. Довідники не чіпаємо.
DATA_TABLES = (
    "notification",
    "photo",
    "confirmation",
    "status_history",
    "request",
    "consent",
    "audit_log",
    "users",
    "contractor",
)


async def _create_test_database() -> None:
    s = get_settings()
    conn = await asyncpg.connect(
        user=s.postgres_user,
        password=s.postgres_password,
        host=s.postgres_host,
        port=s.postgres_port,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", s.postgres_db)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{s.postgres_db}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    """Один раз за запуск: створити тестову БД і застосувати міграції."""
    asyncio.run(_create_test_database())
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    async with SessionLocal() as session:
        await session.execute(text(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE"))
        await session.commit()


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
