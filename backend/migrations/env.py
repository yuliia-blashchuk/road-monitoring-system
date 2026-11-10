"""Налаштування Alembic: звідки брати адресу БД і які моделі відстежувати."""

import asyncio
from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  - реєструє всі таблиці в Base.metadata
from app.core.config import get_settings
from app.core.database import Base

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

target_metadata = Base.metadata
DATABASE_URL = get_settings().database_url


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Порівнюємо лише таблиці проєкту.

    Образ postgis/postgis разом із PostGIS встановлює розширення topology і tiger
    (геокодер адрес США) з десятками службових таблиць. Таблиці, яких немає в
    моделях, і їхні індекси Alembic не чіпає, тому `alembic check` не вимагає
    їх видаляти. Наслідок: видалення моделі не створить DROP TABLE автоматично -
    таку міграцію треба написати вручну.
    """
    if type_ == "table" and reflected and compare_to is None:
        return False
    table = getattr(obj, "table", None)
    if reflected and table is not None and table.name not in target_metadata.tables:
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)


GEO_OPTIONS = {
    "include_object": include_object,
    "process_revision_directives": alembic_helpers.writer,
    "render_item": alembic_helpers.render_item,
}


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        **GEO_OPTIONS,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        **GEO_OPTIONS,
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
