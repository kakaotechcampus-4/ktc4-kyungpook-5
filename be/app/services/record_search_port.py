"""app.ai.RecordSearchPort의 PostgreSQL 구현. 조회마다 짧은 세션을 연다."""

import math

from sqlalchemy import select

from app.ai import ChunkSearchQuery, RecordSource, RetrievedChunk
from app.core.enums import RecordParseStatus
from app.db.session import get_sessionmaker
from app.models.records import Record
from app.models.record_chunks import RecordChunk


class PostgresRecordSearch:
    def __init__(self, club_id: str, *, session_factory=None):
        self.club_id = club_id
        self.session_factory = session_factory

    async def search_chunks(self, query: ChunkSearchQuery) -> tuple[RetrievedChunk, ...]:
        # AI가 잘못된 조직을 요청해도 주입 때 검증한 범위를 넓히지 않는다.
        if query.club_id != self.club_id:
            raise ValueError("검색 범위가 회의의 조직과 다릅니다")
        if not all(math.isfinite(value) for value in query.embedding) or not any(query.embedding):
            raise ValueError("검색 벡터는 유한한 비영 벡터여야 합니다")
        distance = RecordChunk.embedding.cosine_distance(list(query.embedding))
        stmt = (
            select(RecordChunk, Record, distance.label("distance"))
            .join(Record, Record.id == RecordChunk.record_id)
            .where(Record.club_id == self.club_id, Record.parse_status == RecordParseStatus.INDEXED)
        )
        if query.category is not None:
            stmt = stmt.where(Record.category == query.category)
        if query.event_id is not None:
            stmt = stmt.where(Record.event_id == query.event_id)
        stmt = stmt.order_by(distance, RecordChunk.id).limit(min(query.limit, 50))
        factory = self.session_factory or get_sessionmaker()
        async with factory() as session:
            rows = (await session.execute(stmt)).all()
            return tuple(
                RetrievedChunk(
                    text=chunk.text,
                    source=RecordSource(record_id=record.id, file_name=record.file_name, location=chunk.location),
                    category=record.category,
                    event_id=record.event_id,
                    score=max(-1.0, min(1.0, 1.0 - float(cosine_distance))),
                )
                for chunk, record, cosine_distance in rows
            )
