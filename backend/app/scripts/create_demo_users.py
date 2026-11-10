"""Створює демо-користувачів для кожної ролі (лише для локальної розробки й демо).

Запуск:  docker compose exec api python -m app.scripts.create_demo_users
Пароль усіх демо-акаунтів: Demo12345 (можна змінити аргументом --password).
Повторний запуск безпечний: наявні акаунти не змінюються.
"""

import argparse
import asyncio

from sqlalchemy import select

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.enums import ConsentType, ServiceKind
from app.core.security import hash_password
from app.modules.admin.models import Contractor, Service
from app.modules.users import repository as repo
from app.modules.users.models import User

# email, ПІБ, роль, вид служби (для працівників служб)
DEMO_USERS = [
    ("driver@roadmap.local", "Демо Водій", "driver", None),
    ("dispatcher@roadmap.local", "Демо Диспетчер", "dispatcher", ServiceKind.COMMUNAL),
    ("operator@roadmap.local", "Демо Оператор", "operator", ServiceKind.COMMUNAL),
    ("police@roadmap.local", "Демо Інспектор поліції", "dispatcher", ServiceKind.POLICE),
    ("contractor@roadmap.local", "Демо Підрядник", "contractor", None),
    ("admin@roadmap.local", "Демо Адміністратор", "admin", None),
    ("dg@roadmap.local", "Демо Data Governance", "data_governance", None),
]


async def _demo_contractor(session) -> Contractor:
    contractor = await session.scalar(select(Contractor).where(Contractor.edrpou == "00000001"))
    if contractor is None:
        contractor = Contractor(name="ТОВ «Демо Шляхбуд»", edrpou="00000001")
        session.add(contractor)
        await session.flush()
    return contractor


async def main(password: str) -> None:
    settings = get_settings()
    if settings.environment not in {"local", "test", "demo"}:
        raise SystemExit("Демо-користувачі створюються лише в середовищах local / demo")

    async with SessionLocal() as session:
        services = {s.kind: s for s in (await session.scalars(select(Service))).all()}
        for email, name, role_code, service_kind in DEMO_USERS:
            if await repo.get_by_email(session, email):
                print(f"  є      {email}")
                continue
            role = await repo.get_role(session, role_code)
            user = User(
                email=email,
                full_name=name,
                password_hash=hash_password(password),
                role_id=role.id,
                service_id=services[service_kind].id if service_kind else None,
                contractor_id=(await _demo_contractor(session)).id
                if role_code == "contractor"
                else None,
            )
            await repo.add_user(session, user)
            if role_code == "driver":
                await repo.add_consents(
                    session,
                    user,
                    [ConsentType.TERMS, ConsentType.PERSONAL_DATA],
                    settings.consent_version,
                )
            print(f"  додано {email}  ({role_code})")
        await session.commit()
    print(f"Пароль демо-акаунтів: {password}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password", default="Demo12345")
    asyncio.run(main(parser.parse_args().password))
