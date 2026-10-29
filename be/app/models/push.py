"""로그인 계정 소유 Web Push 기기 구독. endpoint/암호 키는 응답·로그에 노출하지 않는다."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ID_LENGTH, IdMixin, TimestampMixin, fk


class PushSubscription(IdMixin, TimestampMixin, Base):
    __tablename__ = "push_subscriptions"
    __id_prefix__ = "psh"
    __table_args__ = (
        UniqueConstraint("endpoint_hash", name="uq_push_subscriptions_endpoint_hash"),
    )

    account_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("accounts.id"), nullable=False, index=True
    )
    endpoint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(100), nullable=False)
    expiration_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(100))
