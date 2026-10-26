"""대화 맥락에서 도출한 할 일 후보.

기존 행사 actions와 분리한다. 수락은 "할 일로 받아들였다"는 기록이고 외부 게시·예약·
송금·업무 완료를 뜻하지 않는다. 실행 경로는 아직 정하지 않았다.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ContextSourceType, TaskSuggestionStatus
from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, enum_column, fk


class TaskSuggestion(IdMixin, TimestampMixin, Base):
    __tablename__ = "task_suggestions"
    __id_prefix__ = "tsk"
    __table_args__ = (Index("ix_task_suggestions_club_status", "club_id", "status"),)

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("context_decisions.id"), nullable=False
    )
    source_type: Mapped[ContextSourceType] = mapped_column(
        enum_column(ContextSourceType), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # 담당·마감을 대화에서 알 수 없으면 null. 사람이 수락하기 전까지 확정 배정이 아니다.
    suggested_assignee: Mapped[str | None] = mapped_column(String(100))
    due_date: Mapped[date | None] = mapped_column(Date)
    # 이 후보가 나온 원문과 그 버전 [{"sourceId", "sourceVersion", ...}]
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JsonB, nullable=False)
    status: Mapped[TaskSuggestionStatus] = mapped_column(
        enum_column(TaskSuggestionStatus),
        nullable=False,
        default=TaskSuggestionStatus.PROPOSED,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    accepted_by: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("members.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
