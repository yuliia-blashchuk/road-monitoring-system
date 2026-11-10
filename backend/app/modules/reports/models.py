"""Заявка та пов'язані записи: Request, Photo, Confirmation, StatusHistory (табл. 13)."""

from datetime import date, datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin
from app.core.enums import PhotoKind, Priority, RequestStatus, pg_enum

MAX_PHOTO_BYTES = 5 * 1024 * 1024  # DQ-04


class Request(CreatedAtMixin, Base):
    __tablename__ = "request"
    __table_args__ = (
        CheckConstraint("char_length(comment) <= 300", name="comment_max_300"),
        CheckConstraint("confirmations_count >= 0", name="confirmations_non_negative"),
        CheckConstraint(
            "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100",
            name="progress_0_100",
        ),
        CheckConstraint(
            "status <> 'rejected' OR reject_reason IS NOT NULL", name="reject_reason_required"
        ),
        # Черга служби: за службою, статусом і пріоритетом.
        Index("ix_request_queue", "service_id", "status", "priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Номер для водія: 1001, 1002, ...
    number: Mapped[int] = mapped_column(Integer, Identity(start=1001), unique=True)
    # NULL після анонімізації (п. 3.7).
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    problem_type_id: Mapped[int] = mapped_column(ForeignKey("problem_type.id"))
    # NULL - правило не знайдено, заявку отримує адміністратор (DQ-12).
    service_id: Mapped[int | None] = mapped_column(ForeignKey("service.id"))
    copy_service_id: Mapped[int | None] = mapped_column(ForeignKey("service.id"), index=True)
    contractor_id: Mapped[int | None] = mapped_column(ForeignKey("contractor.id"), index=True)
    location = mapped_column(Geography("POINT", srid=4326, spatial_index=True), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[RequestStatus] = mapped_column(
        pg_enum(RequestStatus, "request_status"), server_default=RequestStatus.NEW.value
    )
    priority: Mapped[Priority] = mapped_column(
        pg_enum(Priority, "priority"), server_default=Priority.MEDIUM.value
    )
    confirmations_count: Mapped[int] = mapped_column(Integer, server_default="0")
    is_suspicious: Mapped[bool] = mapped_column(Boolean, server_default="false")
    is_reopened: Mapped[bool] = mapped_column(Boolean, server_default="false")
    reject_reason: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[date | None] = mapped_column(Date)
    progress_percent: Mapped[int | None] = mapped_column(Integer)
    # Час створення на пристрої - для офлайн-заявок (DQ-09, data lineage).
    device_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Від нього рахуються терміни зберігання (табл. 17).
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Photo(CreatedAtMixin, Base):
    __tablename__ = "photo"
    __table_args__ = (
        CheckConstraint(f"size_bytes > 0 AND size_bytes <= {MAX_PHOTO_BYTES}", name="size_max_5mb"),
        CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')",
            name="mime_allowed",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("request.id", ondelete="CASCADE"), index=True
    )
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[PhotoKind] = mapped_column(pg_enum(PhotoKind, "photo_kind"))
    storage_key: Mapped[str] = mapped_column(String(255))
    # Розмита копія для публічної карти (п. 3.7).
    storage_key_public: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer)


class Confirmation(CreatedAtMixin, Base):
    """«Теж бачу» / «Все ще є - Вже немає». Один водій - одне підтвердження (DQ-07)."""

    __tablename__ = "confirmation"
    __table_args__ = (
        UniqueConstraint("request_id", "user_id", name="uq_confirmation_request_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("request.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    still_exists: Mapped[bool] = mapped_column(Boolean, server_default="true")


class StatusHistory(Base):
    """Таймлайн статусів. «immutable»: тригер БД забороняє UPDATE і DELETE."""

    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("request.id"), index=True)
    from_status: Mapped[RequestStatus | None] = mapped_column(
        pg_enum(RequestStatus, "request_status")
    )
    to_status: Mapped[RequestStatus] = mapped_column(pg_enum(RequestStatus, "request_status"))
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
