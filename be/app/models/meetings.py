"""회의 세션과 전사 (#135).

실제 오디오·VAD·Whisper·judge_utterance 연동은 이번 범위가 아니다 — WebSocket
세션·발화 순번·영속화·판단 결과 저장 구조만 먼저 실제로 동작하게 만든다.
판단은 더미(services/meeting_judge_stub.py)로 채운다.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import JudgeKind, JudgeRoute, MeetingStatus
from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, enum_column, fk


class Meeting(IdMixin, TimestampMixin, Base):
    __tablename__ = "meetings"
    __id_prefix__ = "mtg"

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False, index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("events.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="ko-KR")
    status: Mapped[MeetingStatus] = mapped_column(
        enum_column(MeetingStatus), nullable=False, default=MeetingStatus.RECORDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_consent_confirmed_by: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("members.id", ondelete="SET NULL")
    )
    recording_consent_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_by: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("members.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="meeting", order_by="TranscriptSegment.seq"
    )


class TranscriptSegment(IdMixin, TimestampMixin, Base):
    """발화 하나. 실제 오디오 대신 test-support로 텍스트를 직접 받는다.

    판단 결과(route/kind/question/answer/sources/trace)는 is_final=true일 때만
    채워진다. 같은 seq가 수정되면(전사 정정) version을 올리고 다시 판단한다 —
    "중복 억제는 하지 않는다"는 AI 쪽 결정(#114)을 그대로 따른다.
    """

    __tablename__ = "transcript_segments"
    __id_prefix__ = "tsg"
    __table_args__ = (
        UniqueConstraint("meeting_id", "seq", name="uq_transcript_segments_meeting_seq"),
    )

    meeting_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("meetings.id"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- 판단 결과. final이 아니면 전부 null ------------------------------
    route: Mapped[JudgeRoute | None] = mapped_column(enum_column(JudgeRoute))
    kind: Mapped[JudgeKind | None] = mapped_column(enum_column(JudgeKind))
    question: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    # model/prompt_version/judge_ms/tool_calls. AI 코드가 채우는 값이라
    # 모델 호출 지연에 영향 없다(#114).
    trace: Mapped[dict[str, Any] | None] = mapped_column(JsonB)

    meeting: Mapped["Meeting"] = relationship(back_populates="segments")
