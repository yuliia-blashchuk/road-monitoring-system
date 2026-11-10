"""Переліки (enum) предметної області. Відповідають «enumeration» з діаграми класів (п. 4.6).

У БД кожен перелік зберігається як тип enum PostgreSQL зі значеннями в нижньому регістрі.
"""

from enum import StrEnum

import sqlalchemy as sa


class RequestStatus(StrEnum):
    NEW = "new"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    DONE = "done"  # «Виконана» підрядником
    RESOLVED = "resolved"  # «Усунена», ставить лише диспетчер (БП-6)
    REJECTED = "rejected"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PhotoKind(StrEnum):
    BEFORE = "before"
    AFTER = "after"
    ACT = "act"


class ServiceKind(StrEnum):
    COMMUNAL = "communal"
    POLICE = "police"


class ConsentType(StrEnum):
    """Типи згоди водія (табл. 15). Обов'язкові: TERMS і PERSONAL_DATA."""

    TERMS = "terms"
    PERSONAL_DATA = "personal_data"
    MEDIA_SHARING = "media_sharing"
    CONTACT = "contact"
    EMAIL_NOTIFICATIONS = "email_notifications"


REQUIRED_CONSENTS = frozenset({ConsentType.TERMS, ConsentType.PERSONAL_DATA})


class AccessScope(StrEnum):
    """Область дії політики доступу (п. 3.4)."""

    OWN = "own"
    SERVICE = "service"
    ALL = "all"
    PUBLIC = "public"


class RoleCode(StrEnum):
    """Коди ролей у таблиці role (табл. 12)."""

    DRIVER = "driver"
    OPERATOR = "operator"
    DISPATCHER = "dispatcher"
    CONTRACTOR = "contractor"
    ADMIN = "admin"
    DATA_GOVERNANCE = "data_governance"


class AccessRole(StrEnum):
    """Роль, за якою шукається політика доступу (стовпці табл. 14).

    operator і dispatcher мають однакові права («Диспетчер»), а працівник служби
    з Service.kind = police отримує права «Поліції».
    """

    DRIVER = "driver"
    DISPATCHER = "dispatcher"
    POLICE = "police"
    CONTRACTOR = "contractor"
    ADMIN = "admin"
    DATA_GOVERNANCE = "data_governance"


class DataLevel(StrEnum):
    """Рівні класифікації даних (табл. 11), від найнижчого до найвищого."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PERSONAL = "personal"


def pg_enum(enum_cls: type[StrEnum], name: str) -> sa.Enum:
    """Тип enum PostgreSQL, що зберігає значення (new), а не імена (NEW)."""
    return sa.Enum(
        enum_cls,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
