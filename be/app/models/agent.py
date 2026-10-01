"""BE ↔ AI 호출 로그.

호출 이력은 빠짐없이 남기고 수정·삭제하지 않는다 (NF4).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AgentFeature, AgentRunStatus
from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, enum_column, fk


class AgentLog(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_log"
    __id_prefix__ = "alg"

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False, index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("events.id", ondelete="SET NULL")
    )
    feature: Mapped[AgentFeature] = mapped_column(
        enum_column(AgentFeature), nullable=False
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_column(AgentRunStatus), nullable=False
    )
    # 민감정보를 마스킹한 뒤 저장한다. 키·토큰은 남기지 않는다.
    request: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    response: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    error: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
