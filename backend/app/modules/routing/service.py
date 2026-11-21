"""RoutingService: визначає службу, службу-копію і початковий пріоритет заявки (F-10, F-23).

Правило RoutingRule підходить, якщо збігається тип проблеми і точка лежить у зоні служби
(Service.zone). Правила зберігаються в БД, тому нове правило адміністратор додає без зміни
коду. Якщо правила немає, заявка лишається без служби й потрапляє адміністратору (DQ-12).

Копія надсилається службі того самого виду, що вказана в правилі, але тій, яка обслуговує
точку: аварію в Шевченківському районі бачить комунальна служба саме цього району.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Priority
from app.modules.admin.models import Service
from app.modules.routing import repository as repo

DEFAULT_PRIORITY = Priority.MEDIUM


@dataclass(frozen=True)
class RoutingResult:
    rule_id: int | None
    service: Service | None
    copy_service: Service | None
    priority: Priority


async def route(
    session: AsyncSession, problem_type_id: int, latitude: float, longitude: float
) -> RoutingResult:
    matches = await repo.matching_rules(session, problem_type_id, latitude, longitude)
    if not matches:
        return RoutingResult(None, None, None, DEFAULT_PRIORITY)

    rule, service = matches[0]
    copy_service = None
    if rule.copy_service_id is not None:
        template = await repo.get_service(session, rule.copy_service_id)
        if template is not None:
            copy_service = await repo.service_in_zone(
                session, template.kind, latitude, longitude, prefer_id=template.id
            )
        if copy_service is not None and copy_service.id == service.id:
            copy_service = None
    return RoutingResult(rule.id, service, copy_service, rule.initial_priority)
