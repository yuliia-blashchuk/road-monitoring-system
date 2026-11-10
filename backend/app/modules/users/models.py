"""Моделі модуля users: Role, User, Consent (табл. 12, п. 3.5)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, CreatedAtMixin
from app.core.enums import ConsentType, pg_enum


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class User(CreatedAtMixin, Base):
    """Користувач. email, full_name, phone - персональні дані (табл. 11)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Зберігається в нижньому регістрі, тому UNIQUE не залежить від регістру.
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(20))
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"), index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("service.id"), index=True)
    contractor_id: Mapped[int | None] = mapped_column(ForeignKey("contractor.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role: Mapped[Role] = relationship(lazy="joined")
    service: Mapped["Service | None"] = relationship(lazy="joined")  # noqa: F821
    consents: Mapped[list["Consent"]] = relationship(back_populates="user", lazy="selectin")


class Consent(Base):
    """Згода водія. Запис не змінюється: відкликання лише заповнює revoked_at."""

    __tablename__ = "consent"
    __table_args__ = (Index("ix_consent_user_id_type", "user_id", "type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[ConsentType] = mapped_column(pg_enum(ConsentType, "consent_type"))
    version: Mapped[str] = mapped_column(String(20))
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="consents")

    def is_active(self, current_version: str | None = None) -> bool:
        if self.revoked_at is not None:
            return False
        return current_version is None or self.version == current_version
