"""Створює базу даних з .env, якщо її ще немає (для запуску без Docker).

Запуск: python -m app.scripts.create_database
У Docker не потрібен: там базу створює контейнер db.
"""

import asyncio

import asyncpg

from app.core.config import get_settings


async def main() -> None:
    s = get_settings()
    try:
        conn = await asyncpg.connect(
            user=s.postgres_user,
            password=s.postgres_password,
            host=s.postgres_host,
            port=s.postgres_port,
            database="postgres",
        )
    except (OSError, asyncpg.PostgresError) as exc:
        raise SystemExit(
            f"Не вдалося підключитися до PostgreSQL на {s.postgres_host}:{s.postgres_port} "
            f"як {s.postgres_user}. Перевір, що PostgreSQL запущений, а користувач і пароль "
            f"у .env правильні.\nДеталі: {exc}"
        ) from exc
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", s.postgres_db)
        if exists:
            print(f"База {s.postgres_db} уже існує")
        else:
            await conn.execute(f'CREATE DATABASE "{s.postgres_db}"')
            print(f"Створено базу {s.postgres_db}")
        postgis = await conn.fetchval(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'"
        )
        if not postgis:
            raise SystemExit(
                "У PostgreSQL не встановлено PostGIS. Встанови його через Stack Builder "
                "(Spatial Extensions → PostGIS) і запусти скрипт ще раз."
            )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
