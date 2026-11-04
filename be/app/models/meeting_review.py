"""회의 종료 후 화자·회의록 검토 상태."""
from typing import Any
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, fk


class MeetingReview(IdMixin, TimestampMixin, Base):
    __tablename__ = 'meeting_reviews'
    __id_prefix__ = 'mrv'

    meeting_id: Mapped[str] = mapped_column(String(ID_LENGTH), fk('meetings.id'), unique=True, nullable=False)
    job_id: Mapped[str] = mapped_column(String(ID_LENGTH), fk('agent_jobs.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provider_job_id: Mapped[str | None] = mapped_column(String(200))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    turns: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    speaker_names: Mapped[dict[str, str] | None] = mapped_column(JsonB)
    # label -> {memberId, name, confirmed}. speaker_names는 기존 FE 호환용이다.
    speaker_mappings: Mapped[dict[str, dict[str, Any]] | None] = mapped_column(JsonB)
    draft: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    candidate_request_id: Mapped[str | None] = mapped_column(String(100))
    candidate_hash: Mapped[str | None] = mapped_column(String(64))
    candidate_ids: Mapped[list[str] | None] = mapped_column(JsonB)
