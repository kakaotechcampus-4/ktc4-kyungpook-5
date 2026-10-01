"""동아리 기록. 과거 행사 문서·장부·공지 등 RAG 원본의 메타데이터."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
