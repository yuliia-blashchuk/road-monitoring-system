"""Правила маршрутизації «тип проблеми → служба → початковий пріоритет» (F-10)."""

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import Priority, pg_enum


class RoutingRule(Base):
    __tablename__ = "routing_rule"
    __table_args__ = (
        UniqueConstraint("problem_type_id", "service_id", name="uq_routing_rule_type_service"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_type_id: Mapped[int] = mapped_column(ForeignKey("problem_type.id"))
    service_id: Mapped[int] = mapped_column(ForeignKey("service.id"))
    # Копія ще одній службі: перешкода - і комунальникам, і поліції.
    copy_service_id: Mapped[int | None] = mapped_column(ForeignKey("service.id"))
    initial_priority: Mapped[Priority] = mapped_column(pg_enum(Priority, "priority"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
