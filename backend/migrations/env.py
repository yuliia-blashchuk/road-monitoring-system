"""Налаштування Alembic: звідки брати адресу БД і які моделі відстежувати."""

import asyncio
import importlib
import pkgutil
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

import app.modules
from app.core.config import get_settings
from app.core.database import Base

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

# Підтягуємо models.py з усіх модулів, щоб Alembic бачив усі таблиці.
for module in pkgutil.iter_modules(app.modules.__path__):
    importlib.import_module(f"app.modules.{module.name}.models")

target_metadata = Base.metadata
DATABASE_URL = get_settings().database_url

# Службові таблиці PostGIS не чіпаємо.
POSTGIS_TABLES = {"spatial_ref_sys"}


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    return not (type_ == "table" and name in POSTGIS_TABLES)


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
