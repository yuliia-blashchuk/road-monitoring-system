"""Демо-набір даних RoadMap (KAN-66): користувачі всіх ролей, підрядники, 53 заявки
з історією статусів, підтвердженнями, сповіщеннями й записами журналу аудиту.

Запуск:  docker compose exec api python -m app.scripts.seed_demo_data
Пароль усіх демо-акаунтів: Demo12345 (можна змінити аргументом --password).

Дані вигадані й знеособлені (п. 3.7): імена «Демо-водій N», адреси @roadmap.local,
без телефонів. Точки й адреси заявок збігаються з демо-картою фронтенду
(frontend/src/data/mapEvents.ts), тож карта виглядає однаково з API і без нього.
Дані узгоджені з правилами системи:
- служба, копія й початковий пріоритет - за правилами маршрутизації (F-10);
- 5+ підтверджень підвищують пріоритет (БП-1); один водій - одне підтвердження (DQ-07);
- коментар є лише в заявках водіїв зі згодою media_sharing (KAN-65);
- історія статусів проходить лише допустимими переходами; «Виконана» ставить
  підрядник, «Усунена» - служба (БП-6); «Відхилена» - з причиною.

Повторний запуск безпечний: акаунти не дублюються, а заявки створюються лише в
порожній базі. Почати з нуля: docker compose down -v, потім docker compose up.
"""

import argparse
import asyncio
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from geoalchemy2 import WKTElement
from sqlalchemy import func, select

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.enums import ConsentType, Priority, RequestStatus
from app.core.security import hash_password
from app.modules.admin.models import Contractor, ProblemType
from app.modules.audit import service as audit
from app.modules.notifications.models import Notification
from app.modules.reports.models import Confirmation, Request, StatusHistory
from app.modules.routing.service import route
from app.modules.users import repository as repo
from app.modules.users.models import User
from app.scripts.create_demo_users import ensure_allowed_environment, ensure_demo_users

S = RequestStatus
C = ConsentType

STATUS_LABELS = {
    S.NEW: "Нова",
    S.ACCEPTED: "Прийнята",
    S.IN_PROGRESS: "В роботі",
    S.DONE: "Виконана",
    S.RESOLVED: "Усунена",
    S.REJECTED: "Відхилена",
}
PRIORITY_UP = {
    Priority.LOW: Priority.MEDIUM,
    Priority.MEDIUM: Priority.HIGH,
    Priority.HIGH: Priority.CRITICAL,
    Priority.CRITICAL: Priority.CRITICAL,
}

# Додаткові водії з різними наборами згод (табл. 15).
DRIVERS = [
    ("driver2@roadmap.local", "Демо-водій 2", [C.MEDIA_SHARING, C.EMAIL_NOTIFICATIONS]),
    ("driver3@roadmap.local", "Демо-водій 3", [C.MEDIA_SHARING, C.CONTACT]),
    ("driver4@roadmap.local", "Демо-водій 4", []),
    ("driver5@roadmap.local", "Демо-водій 5", [C.MEDIA_SHARING]),
    ("driver6@roadmap.local", "Демо-водій 6", [C.EMAIL_NOTIFICATIONS]),
    ("driver7@roadmap.local", "Демо-водій 7", [C.MEDIA_SHARING, C.CONTACT, C.EMAIL_NOTIFICATIONS]),
]
SECOND_CONTRACTOR = ("ТОВ «Демо Дорбуд»", "00000002", "contractor2@roadmap.local")

# Тип на фронтенді -> код у довіднику problem_type.
FRONT_TYPES = {
    "pothole": "pothole",
    "accident": "accident",
    "obstacle": "obstacle",
    "traffic_light": "traffic_light",
    "roadworks": "damaged_surface",
}

# Ті самі точки, що й на демо-карті фронтенду: адреса, тип, статус, широта, довгота.
EVENTS: list[tuple[str, str, str, float, float]] = [
    ("Проспект Свободи", "pothole", "new", 49.8419, 24.0297),
    ("Вулиця Дорошенка", "pothole", "accepted", 49.8398, 24.0262),
    ("Площа Ринок", "obstacle", "new", 49.8418, 24.0320),
    ("Вулиця Городоцька", "roadworks", "in_progress", 49.8377, 24.0187),
    ("Вулиця Личаківська", "accident", "accepted", 49.8381, 24.0460),
    ("Вулиця Івана Франка", "traffic_light", "new", 49.8328, 24.0338),
    ("Проспект Шевченка", "pothole", "resolved", 49.8354, 24.0312),
    ("Вулиця Коперника", "obstacle", "accepted", 49.8386, 24.0228),
    ("Вулиця Винниченка", "pothole", "new", 49.8420, 24.0380),
    ("Вулиця Підвальна", "accident", "resolved", 49.8438, 24.0355),
    ("Вулиця Городоцька", "pothole", "new", 49.8395, 24.0010),
    ("Вулиця Любінська", "roadworks", "in_progress", 49.8242, 23.9925),
    ("Вулиця Виговського", "traffic_light", "accepted", 49.8263, 23.9892),
    ("Вулиця Кульпарківська", "obstacle", "new", 49.8305, 24.0015),
    ("Привокзальна площа", "accident", "accepted", 49.8393, 23.9943),
    ("Вулиця Залізнична", "roadworks", "resolved", 49.8451, 23.9968),
    ("Вулиця Сяйво", "pothole", "new", 49.8380, 23.9763),
    ("Вулиця Широка", "roadworks", "in_progress", 49.8503, 23.9828),
    ("Вулиця Наукова", "pothole", "new", 49.8178, 24.0034),
    ("Вулиця Княгині Ольги", "pothole", "accepted", 49.8218, 24.0090),
    ("Вулиця Володимира Великого", "accident", "new", 49.8165, 24.0153),
    ("Вулиця Сахарова", "roadworks", "in_progress", 49.8264, 24.0179),
    ("Вулиця Стрийська", "traffic_light", "accepted", 49.8216, 24.0208),
    ("Вулиця Героїв УПА", "obstacle", "resolved", 49.8329, 24.0080),
    ("Вулиця Антоновича", "pothole", "new", 49.8316, 24.0058),
    ("Вулиця Кульпарківська", "roadworks", "in_progress", 49.8194, 23.9994),
    ("Проспект Червоної Калини", "pothole", "new", 49.8068, 24.0491),
    ("Вулиця Зелена", "roadworks", "in_progress", 49.8134, 24.0608),
    ("Вулиця Угорська", "accident", "accepted", 49.8164, 24.0379),
    ("Вулиця Сихівська", "traffic_light", "new", 49.8088, 24.0585),
    ("Вулиця Хуторівка", "obstacle", "resolved", 49.8039, 24.0417),
    ("Вулиця Вернадського", "pothole", "accepted", 49.7975, 24.0571),
    ("Вулиця Довженка", "roadworks", "resolved", 49.8057, 24.0581),
    ("Вулиця Демнянська", "obstacle", "new", 49.8064, 24.0242),
    ("Вулиця Шевченка", "pothole", "new", 49.8503, 24.0018),
    ("Проспект Чорновола", "roadworks", "in_progress", 49.8572, 24.0243),
    ("Вулиця Липинського", "accident", "accepted", 49.8617, 24.0395),
    ("Вулиця Замарстинівська", "traffic_light", "new", 49.8648, 24.0269),
    ("Вулиця Варшавська", "pothole", "resolved", 49.8590, 24.0152),
    ("Вулиця Мазепи", "obstacle", "accepted", 49.8676, 24.0229),
    ("Вулиця Богдана Хмельницького", "roadworks", "in_progress", 49.8534, 24.0413),
    ("Вулиця Грінченка", "pothole", "new", 49.8710, 24.0316),
    ("Вулиця Пасічна", "pothole", "new", 49.8316, 24.0702),
    ("Вулиця Личаківська", "accident", "accepted", 49.8365, 24.0601),
    ("Вулиця Зелена", "roadworks", "in_progress", 49.8251, 24.0462),
    ("Вулиця Медової Печери", "obstacle", "new", 49.8292, 24.0738),
    ("Вулиця Джорджа Вашингтона", "traffic_light", "resolved", 49.8274, 24.0851),
    ("Вулиця Пекарська", "pothole", "accepted", 49.8344, 24.0436),
    ("Вулиця Костя Левицького", "pothole", "new", 49.8328, 24.0399),
    ("Вулиця Тракт Глинянський", "roadworks", "resolved", 49.8421, 24.0775),
    # Статуси, яких немає на демо-карті: виконана підрядником, відхилені.
    ("Вулиця Пулюя", "roadworks", "done", 49.8231, 23.9800),
    ("Вулиця Степана Бандери", "pothole", "rejected", 49.8366, 24.0145),
    ("Вулиця Окружна", "obstacle", "rejected", 49.8590, 23.9700),
]

COMMENTS = {
    "pothole": "Глибока яма в правій смузі, машини об'їжджають по зустрічній",
    "accident": "Зіткнення двох авто, перекрито одну смугу",
    "obstacle": "На проїжджій частині впало дерево",
    "traffic_light": "Світлофор не працює, на перехресті затор",
    "damaged_surface": "Покриття розбите на ділянці приблизно 20 м",
}
REJECT_REASONS = [
    "Дублікат заявки на цій ділянці",
    "Некоректне повідомлення: проблему на місці не виявлено",
]


@dataclass
class Staff:
    dispatcher: User  # Залізничний район
    operator: User  # Залізничний район
    dispatcher2: User  # Шевченківський район
    police: User
    admin: User
    contractors: list[tuple[Contractor, User]]

    def handlers(self, service_id: int) -> tuple[list[User], User]:
        """Хто опрацьовує заявку служби і хто ставить «Усунена» (БП-6)."""
        if service_id == self.police.service_id:
            return [self.police], self.police
        if service_id == self.dispatcher2.service_id:
            return [self.dispatcher2], self.dispatcher2
        return [self.dispatcher, self.operator], self.dispatcher


def at(base: datetime, hours: float) -> datetime:
    return base + timedelta(hours=hours)


async def ensure_drivers(session, password: str) -> list[User]:
    """Додаткові водії зі згодами; повертає всіх водіїв (разом із driver@)."""
    version = get_settings().consent_version
    role = await repo.get_role(session, "driver")
    drivers = [await repo.get_by_email(session, "driver@roadmap.local")]
    for email, name, extra in DRIVERS:
        user = await repo.get_by_email(session, email)
        if user is None:
            user = User(
                email=email,
                full_name=name,
                password_hash=hash_password(password),
                role_id=role.id,
            )
            await repo.add_user(session, user)
            for consent in await repo.add_consents(
                session, user, [C.TERMS, C.PERSONAL_DATA, *extra], version
            ):
                audit.record(
                    session,
                    "CONSENT_GRANTED",
                    actor_id=user.id,
                    actor_role="driver",
                    entity_type="consent",
                    entity_id=consent.id,
                    new_value={"type": consent.type.value, "version": version},
                )
            print(f"  додано {email}  (driver)")
        drivers.append(user)
    return drivers


async def ensure_second_contractor(session, password: str) -> tuple[Contractor, User]:
    name, edrpou, email = SECOND_CONTRACTOR
    contractor = await session.scalar(select(Contractor).where(Contractor.edrpou == edrpou))
    if contractor is None:
        contractor = Contractor(name=name, edrpou=edrpou, contact_email="dorbud@roadmap.local")
        session.add(contractor)
        await session.flush()
    user = await repo.get_by_email(session, email)
    if user is None:
        user = User(
            email=email,
            full_name="Демо Підрядник 2",
            password_hash=hash_password(password),
            role_id=(await repo.get_role(session, "contractor")).id,
            contractor_id=contractor.id,
        )
        await repo.add_user(session, user)
        print(f"  додано {email}  (contractor)")
    return contractor, user


async def media_consent_ids(session, drivers: list[User]) -> set[int]:
    result = set()
    for driver in drivers:
        if any(c.type == C.MEDIA_SHARING for c in await repo.active_consents(session, driver.id)):
            result.add(driver.id)
    return result


def status_path(final: S, *, contractor_work: bool) -> list[S]:
    """Допустимий шлях від «Нова» до кінцевого статусу (п. 2.2)."""
    if final == S.NEW:
        return []
    if final == S.REJECTED:
        return [S.REJECTED]
    path = [S.ACCEPTED]
    if final == S.ACCEPTED:
        return path
    path.append(S.IN_PROGRESS)
    if final == S.IN_PROGRESS:
        return path
    if contractor_work:
        path.append(S.DONE)
    if final == S.RESOLVED:
        path.append(S.RESOLVED)
    return path


async def create_reports(session, drivers: list[User], staff: Staff, rng: random.Random) -> int:
    types = {t.code: t for t in (await session.scalars(select(ProblemType))).all()}
    with_media = await media_consent_ids(session, drivers)
    now = datetime.now(UTC).replace(microsecond=0)

    for index, (address, front_type, status_code, lat, lon) in enumerate(EVENTS):
        problem_type = types[FRONT_TYPES[front_type]]
        # Служба, копія й пріоритет - тим самим RoutingService, що й для справжніх заявок.
        rule = await route(session, problem_type.id, lat, lon)
        assert rule.service is not None, f"немає правила для {problem_type.code} у {address}"
        final = S(status_code)
        author = drivers[index % len(drivers)]
        created = now - timedelta(days=rng.randint(1, 30), hours=rng.randint(0, 12))
        contractor_work = problem_type.code in {"damaged_surface", "pothole"} and final in {
            S.IN_PROGRESS,
            S.DONE,
            S.RESOLVED,
        }
        contractor, contractor_user = staff.contractors[index % len(staff.contractors)]

        request = Request(
            author_id=author.id,
            problem_type_id=problem_type.id,
            service_id=rule.service.id,
            copy_service_id=rule.copy_service.id if rule.copy_service else None,
            location=WKTElement(f"POINT({lon} {lat})", srid=4326),
            address=f"{address}, Львів",
            comment=COMMENTS[problem_type.code] if author.id in with_media else None,
            status=final,
            priority=rule.priority,
            created_at=created,
            is_suspicious=index == len(EVENTS) - 1,
            # Обмеження БД: «Відхилена» лише з причиною (БП-3).
            reject_reason=rng.choice(REJECT_REASONS) if final == S.REJECTED else None,
        )
        session.add(request)
        await session.flush()
        audit.record(
            session,
            "REPORT_CREATED",
            actor_id=author.id,
            actor_role="driver",
            entity_type="request",
            entity_id=request.id,
            new_value={
                "problem_type": problem_type.code,
                "service_id": rule.service.id,
                "routing_rule_id": rule.rule_id,
                "priority": rule.priority.value,
            },
        ).created_at = created
        history = [StatusHistory(request_id=request.id, to_status=S.NEW, changed_at=created)]

        # «Теж бачу» від інших водіїв (DQ-07), 5+ підвищують пріоритет (БП-1).
        if final in {S.NEW, S.ACCEPTED, S.IN_PROGRESS}:
            others = [d for d in drivers if d.id != author.id]
            confirmers = rng.sample(others, k=rng.choice([0, 0, 1, 2, 3, 5, 6]))
            for n, driver in enumerate(confirmers, start=1):
                when = at(created, n * 2)
                session.add(Confirmation(request_id=request.id, user_id=driver.id, created_at=when))
                audit.record(
                    session,
                    "REPORT_CONFIRMED",
                    actor_id=driver.id,
                    actor_role="driver",
                    entity_type="request",
                    entity_id=request.id,
                ).created_at = when
            request.confirmations_count = len(confirmers)
            if len(confirmers) >= 5:
                old = request.priority
                request.priority = PRIORITY_UP[old]
                audit.record(
                    session,
                    "PRIORITY_RECALCULATED",
                    entity_type="request",
                    entity_id=request.id,
                    old_value={"priority": old.value},
                    new_value={"priority": request.priority.value, "reason": "БП-1"},
                ).created_at = at(created, 12)

        candidates, closer = staff.handlers(request.service_id)
        handler = rng.choice(candidates)
        previous = S.NEW
        hours = 6.0
        for step in status_path(final, contractor_work=contractor_work):
            when = at(created, hours)
            if step == S.IN_PROGRESS and contractor_work:
                request.contractor_id = contractor.id
                request.deadline = (when + timedelta(days=14)).date()
                request.progress_percent = rng.choice([20, 40, 60, 80])
                audit.record(
                    session,
                    "WORK_ASSIGNED",
                    actor_id=staff.admin.id,
                    actor_role="admin",
                    entity_type="request",
                    entity_id=request.id,
                    new_value={
                        "contractor_id": contractor.id,
                        "deadline": request.deadline.isoformat(),
                    },
                ).created_at = when
            actor = {
                S.DONE: contractor_user,
                S.RESOLVED: closer,
            }.get(step, handler)
            comment = None
            if step == S.REJECTED:
                comment = request.reject_reason
            if step == S.DONE:
                request.progress_percent = 100
                comment = "Роботи завершено, акт додано"
            history.append(
                StatusHistory(
                    request_id=request.id,
                    from_status=previous,
                    to_status=step,
                    changed_by=actor.id,
                    comment=comment,
                    changed_at=when,
                )
            )
            audit.record(
                session,
                "STATUS_CHANGED",
                actor_id=actor.id,
                actor_role=actor.role.code,
                entity_type="request",
                entity_id=request.id,
                old_value={"status": previous.value},
                new_value={"status": step.value},
            ).created_at = when
            session.add(
                Notification(
                    user_id=author.id,
                    request_id=request.id,
                    type="status_changed",
                    message=f"Статус вашої заявки змінено на «{STATUS_LABELS[step]}»",
                    is_read=step != final,
                    created_at=when,
                )
            )
            previous = step
            hours += rng.choice([4, 12, 24, 48])
        if final in {S.RESOLVED, S.REJECTED}:
            request.closed_at = history[-1].changed_at
        session.add_all(history)
    return len(EVENTS)


async def add_security_events(session, drivers: list[User], staff: Staff) -> None:
    """Кілька подій безпеки для сторінки журналу аудиту (KAN-67)."""
    now = datetime.now(UTC)
    events = [
        ("LOGIN_SUCCESS", staff.dispatcher, "success", None, timedelta(hours=5)),
        ("LOGIN_FAILED", None, "denied", {"reason": "bad_credentials"}, timedelta(hours=4)),
        (
            "ACCESS_DENIED",
            drivers[0],
            "denied",
            {"action": "view", "endpoint": "GET /api/v1/audit", "reason": "no_policy"},
            timedelta(hours=3),
        ),
        (
            "ACCESS_DENIED",
            staff.police,
            "denied",
            {
                "action": "view_internal",
                "endpoint": "GET /api/v1/reports/1001",
                "reason": "out_of_scope:service",
            },
            timedelta(hours=2),
        ),
    ]
    for action, user, result, value, ago in events:
        # Відмови пишуться з роллю політики: працівник служби kind = police - «police».
        role = user.role.code if user else None
        if action == "ACCESS_DENIED" and user is staff.police:
            role = "police"
        audit.record(
            session,
            action,
            actor_id=user.id if user else None,
            actor_role=role,
            result=result,
            new_value=value,
        ).created_at = now - ago


async def seed(password: str) -> None:
    ensure_allowed_environment()
    rng = random.Random(66)  # однаковий набір при кожному запуску
    async with SessionLocal() as session:
        users = await ensure_demo_users(session, password)
        drivers = await ensure_drivers(session, password)
        second = await ensure_second_contractor(session, password)
        await session.flush()
        # Перечитуємо користувачів разом із роллю (для нових об'єктів її ще не завантажено).
        users = {email: await repo.get_by_id(session, u.id) for email, u in users.items()}
        drivers = [await repo.get_by_id(session, d.id) for d in drivers]
        second = (second[0], await repo.get_by_id(session, second[1].id))
        contractor_one = await session.scalar(
            select(Contractor).where(Contractor.edrpou == "00000001")
        )
        staff = Staff(
            dispatcher=users["dispatcher@roadmap.local"],
            operator=users["operator@roadmap.local"],
            dispatcher2=users["dispatcher2@roadmap.local"],
            police=users["police@roadmap.local"],
            admin=users["admin@roadmap.local"],
            contractors=[
                (contractor_one, users["contractor@roadmap.local"]),
                second,
            ],
        )
        if await session.scalar(select(func.count()).select_from(Request)):
            print("  заявки вже є - пропускаємо (почати з нуля: docker compose down -v)")
        else:
            count = await create_reports(session, drivers, staff, rng)
            await add_security_events(session, drivers, staff)
            print(f"  додано заявок з історією статусів: {count}")
        await session.commit()
    print(f"Пароль демо-акаунтів: {password}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password", default="Demo12345")
    asyncio.run(seed(parser.parse_args().password))
