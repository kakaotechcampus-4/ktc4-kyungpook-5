"""회의 세션, 음성 청크, 전사 (#135).

실제 VAD·Whisper·judge_utterance 연동은 아직 없다. 음성 청크는 저장만 하고
전사는 더미 STT(services/meeting_stt_stub.py)나 test-support 주입으로 만든다.
판단 결과는 context_decisions에 따로 남긴다.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import MeetingStatus
from app.db.base import Base, ID_LENGTH, IdMixin, TimestampMixin, enum_column, fk


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
    # 전사가 생기거나 고쳐질 때마다 1씩 커진다. GET .../transcripts?afterSeq=의 cursor.
    transcript_cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="meeting", order_by="TranscriptSegment.seq"
    )


class MeetingAudioChunk(IdMixin, TimestampMixin, Base):
    """업로드한 음성 청크. 파일 바이트는 DB가 아니라 저장소에 둔다.

    같은 seq로 같은 파일이 다시 오면 기존 청크를 돌려주고, 다른 파일이면 409다.
    """

    __tablename__ = "meeting_audio_chunks"
    __id_prefix__ = "auc"
    __table_args__ = (
        UniqueConstraint("meeting_id", "seq", name="uq_meeting_audio_chunks_meeting_seq"),
    )

    meeting_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("meetings.id"), nullable=False
    )
    # 업로드 순서. 전사 seq와 다른 축이다.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    job_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("agent_jobs.id"), nullable=False
    )


class TranscriptSegment(IdMixin, TimestampMixin, Base):
    """발화 하나. 판단의 근거(source)이며 id·version으로 참조된다.

    같은 seq가 정정되면 version을 올리고, 이전 판단은 STALE로 두고 다시 판단한다 —
    "중복 억제는 하지 않는다"는 AI 쪽 결정(#114)을 그대로 따른다.
    is_final=false인 전사는 표시만 하고 판단하지 않는다.
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
    # 화자 구분 라벨. 동아리원 계정과 매칭된 값이 아니다.
    speaker_label: Mapped[str | None] = mapped_column(String(100))
    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    # 이 전사가 마지막으로 생기거나 고쳐졌을 때의 Meeting.transcript_cursor 값.
    change_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # STT로 만든 전사면 원본 청크. test-support 주입이면 null.
    audio_chunk_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("meeting_audio_chunks.id", ondelete="SET NULL")
    )
    # 현재 version에 대한 판단 작업. final이 아니면 null.
    decision_job_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("agent_jobs.id", ondelete="SET NULL")
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="segments")
