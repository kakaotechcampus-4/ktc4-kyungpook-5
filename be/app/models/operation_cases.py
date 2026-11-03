"""운영 상황 입력과 확인 결과의 영속 상태."""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, fk


class OperationCase(IdMixin, TimestampMixin, Base):
    __tablename__ = 'operation_cases'
    __id_prefix__ = 'opc'
    __table_args__ = (UniqueConstraint('event_id', 'client_request_id', name='uq_operation_case_request'),)

    event_id: Mapped[str] = mapped_column(String(ID_LENGTH), fk('events.id'), nullable=False, index=True)
    client_request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    action_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), fk('actions.id', ondelete='SET NULL'))
    question_status: Mapped[str] = mapped_column(String(20), nullable=False, default='PENDING')
    result_status: Mapped[str] = mapped_column(String(20), nullable=False, default='NOT_REQUESTED')
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    attempt_id: Mapped[str | None] = mapped_column(String(32))
    attempt_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
