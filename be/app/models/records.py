"""동아리 기록. 과거 행사 문서·장부·공지 등 RAG 원본의 메타데이터."""

from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.ai import EMBEDDING_DIMENSIONS
from app.core.enums import RecordCategory, RecordFileType, RecordParseStatus
from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, enum_column, fk

if TYPE_CHECKING:
    from app.models.clubs import Club
    from app.models.events import Event


class Record(IdMixin, TimestampMixin, Base):
    __tablename__ = "records"
    __id_prefix__ = "rec"
    __table_args__ = (
        Index("ix_records_club_category", "club_id", "category"),
        {"comment": "동아리 기록 원본 메타데이터"},
    )

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False
    )
    # 특정 행사에 속하지 않는 회칙·공지도 있어 nullable이다.
    event_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("events.id", ondelete="SET NULL")
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[RecordFileType] = mapped_column(
        enum_column(RecordFileType), nullable=False
    )
    category: Mapped[RecordCategory] = mapped_column(
        enum_column(RecordCategory), nullable=False
    )
    # S3 경로
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    # bytes
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parse_status: Mapped[RecordParseStatus] = mapped_column(
        enum_column(RecordParseStatus), nullable=False
    )
    parse_result: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    # 읽기 실패 원인. 화면에 사유와 해결 방법을 보여주므로 형식을 schemas에서 고정한다.
    parse_error: Mapped[dict[str, Any] | None] = mapped_column(JsonB)

    club: Mapped["Club"] = relationship(back_populates="records")
    event: Mapped["Event | None"] = relationship()
    chunks: Mapped[list["RecordChunk"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class RecordChunk(IdMixin, TimestampMixin, Base):
    """기록 하나를 조각낸 검색 단위. app.ai.index_record가 만든 청크를 저장한다.

    club_id·file_name·category·event_id는 검색 필터링과 출처 표시를 위해 Record에서
    그대로 복사해둔다 — 검색마다 Record와 조인하지 않기 위해서다.
    """

    __tablename__ = "record_chunks"
    __id_prefix__ = "chk"
    __table_args__ = (
        Index("ix_record_chunks_club_category", "club_id", "category"),
        {"comment": "기록 검색용 청크(임베딩 포함)"},
    )

    record_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("records.id", ondelete="CASCADE"), nullable=False
    )
    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[RecordCategory] = mapped_column(
        enum_column(RecordCategory), nullable=False
    )
    event_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("events.id", ondelete="SET NULL")
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    location_label: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=False
    )

    record: Mapped["Record"] = relationship(back_populates="chunks")
