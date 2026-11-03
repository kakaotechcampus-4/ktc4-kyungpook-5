"""사용자가 확인한 일정·할 일과 지정 수신자의 한 번 알림.

후보 ACCEPTED와 분리한다. SERVICE_ACCEPTED는 Push 서비스의 접수이며,
기기에 표시됐다는 확인이 아니다.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, fk


class ConfirmedTask(IdMixin, TimestampMixin, Base):
    __tablename__ = "confirmed_tasks"
    __id_prefix__ = "ctk"
    __table_args__ = (
        UniqueConstraint("suggestion_id", name="uq_confirmed_tasks_suggestion"),
        Index("ix_confirmed_tasks_club_status", "club_id", "status"),
    )

    club_id: Mapped[str] = mapped_column(String(ID_LENGTH), fk("clubs.id"), nullable=False)
    suggestion_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("task_suggestions.id"), nullable=False
    )
    # 최초 확인의 입력 버전과 정규화된 본문 해시. 재전송은 예약을 만들지 않는다.
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # 담당자와 알림 수신자는 별개다. 계정 매칭이 불확실하면 이름만 보관한다.
    assignee_name: Mapped[str | None] = mapped_column(String(100))
    assignee_account_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("accounts.id", ondelete="SET NULL")
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    confirmed_by: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("members.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    reminder: Mapped["TaskReminder"] = relationship(
        back_populates="item", lazy="selectin", uselist=False, passive_deletes=True
    )


class TaskReminder(IdMixin, TimestampMixin, Base):
    __tablename__ = "task_reminders"
    __id_prefix__ = "rmd"
    __table_args__ = (
        UniqueConstraint("confirmed_item_id", name="uq_task_reminders_item"),
        Index("ix_task_reminders_status_at", "status", "reminder_at"),
    )

    club_id: Mapped[str] = mapped_column(String(ID_LENGTH), fk("clubs.id"), nullable=False)
    confirmed_item_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("confirmed_tasks.id"), nullable=False
    )
    reminder_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recipient_account_ids: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    item: Mapped[ConfirmedTask] = relationship(back_populates="reminder")
