"""Сповіщення в застосунку (табл. 12). Зберігаються 90 днів (табл. 17)."""

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin


class Notification(CreatedAtMixin, Base):
    __tablename__ = "notification"
    __table_args__ = (Index("ix_notification_user_unread", "user_id", "is_read"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[int | None] = mapped_column(ForeignKey("request.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, server_default="false")
