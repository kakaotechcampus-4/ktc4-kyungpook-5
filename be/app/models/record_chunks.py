"""AI 청크의 영구 저장. 권한 범위와 원문 위치는 BE가 붙인다."""

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.ai import EMBEDDING_DIMENSIONS
from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, fk


class RecordChunk(IdMixin, TimestampMixin, Base):
    __tablename__ = "record_chunks"
    __id_prefix__ = "rck"
    __table_args__ = (
        UniqueConstraint("record_id", "chunk_index"),
        Index("ix_record_chunks_record_id", "record_id"),
    )

    record_id: Mapped[str] = mapped_column(String(ID_LENGTH), fk("records.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[dict] = mapped_column(JsonB, nullable=False)
    block_indexes: Mapped[list[int]] = mapped_column(JsonB, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS), nullable=False)
