"""Імпорт усіх моделей, щоб SQLAlchemy й Alembic бачили всі таблиці і зв'язки між модулями."""

from app.modules.admin.models import (  # noqa: F401
    AccessPolicy,
    CityBoundary,
    Contractor,
    ProblemType,
    Service,
)
from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.notifications.models import Notification  # noqa: F401
from app.modules.reports.models import Confirmation, Photo, Request, StatusHistory  # noqa: F401
from app.modules.routing.models import RoutingRule  # noqa: F401
from app.modules.users.models import Consent, Role, User  # noqa: F401
