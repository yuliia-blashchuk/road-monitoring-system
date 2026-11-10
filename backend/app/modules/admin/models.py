"""Довідники й доступ: ProblemType, Service, Contractor, CityBoundary, AccessPolicy."""

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import AccessScope, ServiceKind, pg_enum


class ProblemType(Base):
    """Довідник типів проблем (яма, аварія, ...). Публічні дані."""

    __tablename__ = "problem_type"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    icon: Mapped[str] = mapped_column(String(50))
    color: Mapped[str] = mapped_column(String(7))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    __table_args__ = (CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name="color_hex"),)


class Service(Base):
    """Служба (комунальна або поліція) із зоною відповідальності."""

    __tablename__ = "service"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[ServiceKind] = mapped_column(pg_enum(ServiceKind, "service_kind"))
    zone = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(254))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Contractor(Base):
    """Реєстр підрядників. Конфіденційні дані."""

    __tablename__ = "contractor"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    edrpou: Mapped[str] = mapped_column(String(8), unique=True)
    contact_email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    __table_args__ = (CheckConstraint("edrpou ~ '^[0-9]{8}$'", name="edrpou_8_digits"),)


class CityBoundary(Base):
    """Межа міста для перевірки DQ-03 (ST_Contains). Відкрите питання п. 4.5 - окрема таблиця."""

    __tablename__ = "city_boundary"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False)


class AccessPolicy(Base):
    """Правило доступу «роль × ресурс × дія → область дії» (клас AccessPolicy, табл. 14).

    Якщо політики немає - доступ заборонено (заборонено за замовчуванням).
    log_access = True - кожне використання дозволу окремо пишеться в AuditLog («*» у табл. 14).
    """

    __tablename__ = "access_policy"
    __table_args__ = (
        UniqueConstraint(
            "role", "resource", "action", name="uq_access_policy_role_resource_action"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(32))
    resource: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(50))
    scope: Mapped[AccessScope] = mapped_column(pg_enum(AccessScope, "access_scope"))
    log_access: Mapped[bool] = mapped_column(Boolean, server_default="false")
